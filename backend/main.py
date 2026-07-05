"""
main.py — FastAPI entry point with multi-stream, per-camera zones, and WebSocket alerts
"""

import cv2
import json
import asyncio
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Dict
from contextlib import asynccontextmanager
from queue import Queue
from threading import Thread
from dataclasses import dataclass

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
import hashlib
import secrets
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from datetime import datetime, timedelta

from db.database import engine, get_db
from db.models import Base, IntrusionEvent, User
from detection.detector import PersonDetector
from detection.zones import ZoneManager, Zone
from stream_manager import StreamManager, CameraConfig, setup_test_cameras
from zone_config import ZoneConfigManager


# Create tables
Base.metadata.create_all(bind=engine)

# Global state
detector = None
stream_manager = None
zone_config_manager = None
latest_frames: Dict[str, np.ndarray] = {}
latest_detections: Dict[str, List] = {}
zone_managers: Dict[str, ZoneManager] = {}
active_connections: List[WebSocket] = []
alert_queue = Queue()
_loop = None

security = HTTPBearer()
JWT_SECRET = "your-secret-key-change-this-in-production"
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 8

def hash_password(password: str) -> str:
    """Simple secure hash using SHA-256 with salt."""
    salt = secrets.token_hex(16)
    hashed = hashlib.sha256((password + salt).encode()).hexdigest()
    return f"{salt}${hashed}"

def verify_password(plain: str, hashed: str) -> bool:
    """Verify password against stored hash."""
    try:
        salt, stored_hash = hashed.split("$", 1)
        computed = hashlib.sha256((plain + salt).encode()).hexdigest()
        return secrets.compare_digest(computed, stored_hash)
    except ValueError:
        return False

def create_token(username: str, role: str) -> str:
    payload = {
        "sub": username,
        "role": role,
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRE_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    payload = decode_token(credentials.credentials)
    return {"username": payload["sub"], "role": payload["role"]}

def require_admin(user: dict = Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def init_system():
    """Initialize detection system with multi-stream support."""
    global detector, stream_manager, zone_config_manager

    detector = PersonDetector(model_name="yolov8n.pt", conf_threshold=0.5)
    stream_manager = setup_test_cameras()
    zone_config_manager = ZoneConfigManager()

    print("[System] Multi-stream detection initialized")

    # Seed default users if none exist
    db = next(get_db())
    try:
        if db.query(User).count() == 0:
            admin = User(
                username="admin",
                password_hash=hash_password("admin"),
                role="admin"
            )
            guard = User(
                username="guard",
                password_hash=hash_password("guard"),
                role="guard"
            )
            db.add_all([admin, guard])
            db.commit()
            print("[System] Default users created: admin/admin, guard/guard")
    finally:
        db.close()


def process_alert_queue():
    """Background thread to process alerts from queue using the event loop."""
    global _loop
    while True:
        try:
            event = alert_queue.get(timeout=1)
            if _loop and _loop.is_running():
                asyncio.run_coroutine_threadsafe(broadcast_alert(event), _loop)
            alert_queue.task_done()
        except Exception:
            continue


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    global _loop
    _loop = asyncio.get_running_loop()

    # Start background alert processor thread
    alert_thread = Thread(target=process_alert_queue, daemon=True)
    alert_thread.start()

    init_system()
    yield

    # Cleanup
    if stream_manager:
        stream_manager.release_all()
    print("[System] Shutdown complete")


app = FastAPI(
    title="Smart Intrusion Detection API",
    description="Real-time multi-camera intrusion detection with YOLOv8",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================== WEBSOCKET ====================


async def broadcast_alert(event: dict):
    """Send alert to all connected WebSocket clients."""
    message = {
        "type": "intrusion_alert",
        "data": event,
        "timestamp": datetime.now().isoformat(),
    }
    disconnected = []
    for conn in active_connections:
        try:
            await conn.send_json(message)
        except Exception:
            disconnected.append(conn)

    for conn in disconnected:
        if conn in active_connections:
            active_connections.remove(conn)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket for real-time alerts."""
    await websocket.accept()
    active_connections.append(websocket)
    print(f"[WebSocket] Client connected. Total: {len(active_connections)}")

    try:
        while True:
            data = await asyncio.wait_for(websocket.receive_text(), timeout=60.0)
            if data == "ping":
                await websocket.send_text("pong")
    except asyncio.TimeoutError:
        print("[WebSocket] Timeout, closing connection")
    except WebSocketDisconnect:
        print("[WebSocket] Client disconnected normally")
    except Exception as e:
        print(f"[WebSocket] Error: {e}")
    finally:
        if websocket in active_connections:
            active_connections.remove(websocket)
        try:
            await websocket.close()
        except Exception:
            pass
        print(f"[WebSocket] Client removed. Total: {len(active_connections)}")


# ==================== VIDEO STREAMING ====================


def generate_frames(camera_id: str = "cam1"):
    """Generator for MJPEG stream. Plays once, then holds last frame."""
    cap = stream_manager.get_capture(camera_id)
    if not cap:
        # Return error frame
        while True:
            frame = np.zeros((432, 768, 3), dtype=np.uint8)
            cv2.putText(
                frame,
                f"CAMERA NOT FOUND: {camera_id}",
                (150, 216),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 0, 255),
                2,
            )
            _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            frame_bytes = buffer.tobytes()
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
            )

    # Load zones for this camera
        # Load zones for this camera (use defaults if none saved)
    zones = zone_config_manager.load_zones(camera_id)
    
    # If no custom zones, use defaults
    if not zones:
        zones = [
            Zone(
                name="Server Room",
                points=[(400, 150), (700, 150), (700, 350), (400, 350)],
                color=(0, 0, 255),
                severity="high"
            ),
            Zone(
                name="Storage Area",
                points=[(50, 100), (250, 100), (250, 300), (50, 300)],
                color=(255, 165, 0),
                severity="medium"
            )
        ]
    
    if camera_id not in zone_managers:
        zone_managers[camera_id] = ZoneManager()
        for zone in zones:
            zone_managers[camera_id].add_zone(zone)

    cam_zone_manager = zone_managers[camera_id]

    fps = cap.get(cv2.CAP_PROP_FPS) or 12.0
    width, height = 768, 432

    video_ended = False
    last_frame = None
    frame_count = 0

    print(f"[Stream] Starting stream for {camera_id}")

    while True:
        # Reload zones every 30 seconds to pick up changes
        if frame_count % (int(fps) * 30) == 0:  # Every 30 seconds
            new_zones = zone_config_manager.load_zones(camera_id)
            if new_zones:
                zone_managers[camera_id] = ZoneManager()
                for zone in new_zones:
                    zone_managers[camera_id].add_zone(zone)
                cam_zone_manager = zone_managers[camera_id]
                print(f"[Stream] Reloaded {len(new_zones)} zones for {camera_id}")

        frame_count += 1

        if not video_ended:
            ret, frame = cap.read()
            if not ret:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue
            else:
                last_frame = frame.copy()

        # Use last good frame if video ended
        frame = (
            last_frame.copy()
            if last_frame is not None
            else np.zeros((height, width, 3), dtype=np.uint8)
        )

        frame = cv2.resize(frame, (width, height))

        # Run detection
        annotated, detections = detector.detect(frame.copy())

        # Check intrusions using camera-specific zone manager
        annotated, events = cam_zone_manager.check_intrusion(annotated, detections)

        # Queue events for async processing
        for event in events:
            snapshot_dir = Path("snapshots") / camera_id
            snapshot_dir.mkdir(parents=True, exist_ok=True)
            snapshot_path = (
                snapshot_dir
                / f"event_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.jpg"
            )
            cv2.imwrite(str(snapshot_path), annotated)
            event["snapshot"] = str(snapshot_path)
            event["camera_id"] = camera_id

            alert_queue.put(event)

            # Save to DB
            db = None
            try:
                db = next(get_db())
                db_event = IntrusionEvent(
                    zone_name=event["zone_name"],
                    camera_id=camera_id,
                    confidence=event["confidence"],
                    severity=event["severity"],
                    snapshot_path=str(snapshot_path),
                    bbox_x1=event["bbox"][0],
                    bbox_y1=event["bbox"][1],
                    bbox_x2=event["bbox"][2],
                    bbox_y2=event["bbox"][3],
                )
                db.add(db_event)
                db.commit()
                db.refresh(db_event)
                event["id"] = db_event.id
            except Exception as e:
                print(f"[DB Error] {e}")
            finally:
                if db:
                    db.close()

        latest_frames[camera_id] = annotated
        latest_detections[camera_id] = detections

        # Overlay info
        person_count = len(detections)
        info = f"Cam: {camera_id} | Persons: {person_count} | Zones: {len(zones)}"
        cv2.putText(annotated, info, (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        # Add "VIDEO ENDED" overlay if done
        if video_ended:
            cv2.putText(
                annotated,
                "STREAM ENDED - NO ACTIVE FEED",
                (180, 216),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 0, 255),
                2,
            )

        # Encode to JPEG
        _, buffer = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 70])
        frame_bytes = buffer.tobytes()

        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
        )

    cap.release()


@app.get("/stream/{camera_id}")
async def video_stream(camera_id: str):
    """MJPEG video stream endpoint for specific camera."""
    return StreamingResponse(
        generate_frames(camera_id),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


# ==================== CAMERA MANAGEMENT ====================


@app.get("/cameras")
async def get_cameras():
    """List all configured cameras."""
    return stream_manager.list_cameras()


@app.post("/cameras")
async def add_camera(config: CameraConfig):
    """Add a new camera."""
    stream_manager.add_camera(config)
    return {"message": "Camera added", "camera": config.id}


# ==================== ZONE MANAGEMENT ====================


@app.get("/zones/{camera_id}")
async def get_camera_zones(camera_id: str):
    """Get zones for a specific camera."""
    zones = zone_config_manager.load_zones(camera_id)
    return [
        {
            "name": z.name,
            "points": z.points,
            "color": z.color,
            "severity": z.severity,
        }
        for z in zones
    ]


@app.post("/zones/{camera_id}")
async def save_zones(camera_id: str, zones: List[dict]):
    """Save zones for a specific camera."""
    zone_config_manager.save_zones(camera_id, zones)
    return {"message": f"Saved {len(zones)} zones for {camera_id}"}


@app.delete("/zones/{camera_id}")
async def delete_zones(camera_id: str):
    """Delete zone config for a camera."""
    zone_config_manager.delete_zones(camera_id)
    return {"message": f"Deleted zones for {camera_id}"}


# ==================== REST API ====================


@app.get("/")
async def root():
    return {
        "message": "Smart Intrusion Detection API",
        "version": "2.0.0",
        "features": ["multi-stream", "per-camera-zones", "websocket-alerts"],
        "status": "running",
    }


@app.get("/alerts", response_model=List[dict])
async def get_alerts(
    limit: int = Query(50, ge=1, le=500),
    resolved: Optional[bool] = None,
    camera_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Get intrusion alerts with optional filters."""
    query = db.query(IntrusionEvent)

    if resolved is not None:
        query = query.filter(IntrusionEvent.resolved == resolved)

    events = query.order_by(IntrusionEvent.timestamp.desc()).limit(limit).all()
    return [e.to_dict() for e in events]


@app.post("/alerts/{event_id}/resolve")
async def resolve_alert(event_id: int, db: Session = Depends(get_db)):
    """Mark an alert as resolved."""
    event = db.query(IntrusionEvent).filter(IntrusionEvent.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    event.resolved = True
    db.commit()
    return {"message": "Event resolved", "event": event.to_dict()}


@app.get("/stats")
async def get_stats(db: Session = Depends(get_db)):
    """Get system statistics."""
    total_events = db.query(IntrusionEvent).count()
    unresolved = db.query(IntrusionEvent).filter(IntrusionEvent.resolved == False).count()

    return {
        "total_events": total_events,
        "unresolved_events": unresolved,
        "cameras": len(stream_manager.cameras) if stream_manager else 0,
        "streaming": True,
    }


@app.post("/auth/login")
async def login(credentials: dict, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == credentials.get("username")).first()
    if not user or not verify_password(credentials.get("password", ""), user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    token = create_token(user.username, user.role)
    return {"token": token, "username": user.username, "role": user.role}

@app.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return user

@app.delete("/alerts/all")
async def clear_all_alerts(
    admin: dict = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Clear all intrusion events (admin only)."""
    count = db.query(IntrusionEvent).count()
    db.query(IntrusionEvent).delete()
    db.commit()
    return {"message": f"Cleared {count} events"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)