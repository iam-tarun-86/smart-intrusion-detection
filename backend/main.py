"""
main.py — FastAPI entry point with multi-stream, per-camera zones, and WebSocket alerts
"""

import cv2
import json
import asyncio
import numpy as np
import time
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
from telegram_notifier import TelegramNotifier
import os

def load_env(dotenv_path: str = ".env"):
    """Load variables from .env file into os.environ if it exists."""
    paths = [
        Path(dotenv_path),
        Path(__file__).parent / dotenv_path,
        Path(__file__).parent.parent / dotenv_path
    ]
    for path in paths:
        if path.exists() and path.is_file():
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, val = line.split("=", 1)
                        key = key.strip()
                        val = val.strip()
                        if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
                            val = val[1:-1]
                        os.environ.setdefault(key, val)
            break

load_env()


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
telegram = None

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

    global telegram
    telegram_bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not telegram_bot_token:
        print("[System] WARNING: TELEGRAM_BOT_TOKEN is not set in environment variables")
    telegram = TelegramNotifier(
        bot_token=telegram_bot_token,
        chat_id=os.environ.get("TELEGRAM_CHAT_ID", "5037779190")
    )
    print("[System] Telegram notifier initialized")

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

# Camera-specific uniform rules
CAMERA_UNIFORM_RULES = {
    "cam1": ["blue"],           # Server Room: blue only
    "cam2": ["blue", "white"],  # Parking Lot: blue + white allowed
    "webcam": [],               # Webcam: no enforcement (showcase mode)
}


def is_live_source(source: str) -> bool:
    """Check if the camera source is a live feed (RTSP, webcam, etc.) or a file."""
    source_str = str(source).strip()
    if source_str.isdigit():
        return True
    if source_str.lower().startswith(("rtsp://", "rtmp://", "http://", "https://", "udp://")):
        return True
    return False


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

    # Load zones for this camera (empty = camera-wide uniform check)
    zones = zone_config_manager.load_zones(camera_id)
    
    if camera_id not in zone_managers:
        allowed_colors = CAMERA_UNIFORM_RULES.get(camera_id, [])
        enforce_uniform = len(allowed_colors) > 0
        zone_managers[camera_id] = ZoneManager(
            camera_name=camera_id,
            enforce_uniform=enforce_uniform,
            default_allowed=allowed_colors
        )
        for zone in zones:
            zone_managers[camera_id].add_zone(zone)
        
        if not zones and enforce_uniform:
            print(f"[ZoneManager] {camera_id}: No zones — camera-wide uniform enforcement (blue only)")
        elif not zones:
            print(f"[ZoneManager] {camera_id}: No zones — detection only, no uniform check")

    cam_zone_manager = zone_managers[camera_id]

    fps = cap.get(cv2.CAP_PROP_FPS) or 12.0
    width, height = 768, 432

    video_ended = False
    connection_lost = False
    reconnect_attempts = 0
    
    camera_config = stream_manager.cameras.get(camera_id)
    source = camera_config.source if camera_config else "0"
    is_live = is_live_source(source)

    last_frame = None
    frame_count = 0
    is_night_mode = False

    print(f"[Stream] Starting stream for {camera_id} (Live: {is_live})")

    while True:
        # Reload zones every 30 seconds to pick up changes
        if frame_count % (int(fps) * 30) == 0:  # Every 30 seconds
            new_zones = zone_config_manager.load_zones(camera_id)
            if new_zones:
                allowed_colors = CAMERA_UNIFORM_RULES.get(camera_id, [])
                enforce_uniform = len(allowed_colors) > 0
                zone_managers[camera_id] = ZoneManager(
                    camera_name=camera_id,
                    enforce_uniform=enforce_uniform,
                    default_allowed=allowed_colors
                )
                for zone in new_zones:
                    zone_managers[camera_id].add_zone(zone)
                cam_zone_manager = zone_managers[camera_id]
                print(f"[Stream] Reloaded {len(new_zones)} zones for {camera_id}")

        frame_count += 1

        if connection_lost:
            # Create a black frame with reconnect status
            last_annotated_frame = np.zeros((height, width, 3), dtype=np.uint8)
            cv2.putText(
                last_annotated_frame,
                f"CAMERA DISCONNECTED - RETRYING (Attempt {reconnect_attempts})...",
                (50, 216),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 165, 255),
                2,
            )
            # Encode and yield
            _, buffer = cv2.imencode(".jpg", last_annotated_frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n"
            )
            
            # Try to reconnect
            time.sleep(3.0)
            reconnect_attempts += 1
            cap.release()
            cap = stream_manager.get_capture(camera_id)
            if cap and cap.isOpened():
                print(f"[Stream] Camera {camera_id} successfully reconnected!")
                connection_lost = False
                reconnect_attempts = 0
            continue

        if not video_ended and not connection_lost:
            ret, frame = cap.read()
            if not ret:
                if is_live:
                    connection_lost = True
                    print(f"[Stream] Connection lost for camera {camera_id}. Retrying...")
                    continue
                else:
                    video_ended = True
                    print(f"[Stream] Video ended for {camera_id}. Holding last frame and stopping detection.")
            else:
                last_frame = frame.copy()

        if not video_ended and not connection_lost and last_frame is not None:
            frame_resized = cv2.resize(last_frame, (width, height))

            # Detect Night Mode (Thermal/IR)
            is_night_mode = ZoneManager.check_is_night_mode(frame_resized)

            # Run detection
            annotated, detections = detector.detect(frame_resized.copy())

            # Check intrusions using camera-specific zone manager (pass is_night_mode)
            annotated, events = cam_zone_manager.check_intrusion(annotated, detections, is_night_mode=is_night_mode)

            # Queue events for async processing
            for event in events:
                # Ensure track_id and duration_seconds exist on the event dict
                event["track_id"] = event.get("track_id", 0)
                event["duration_seconds"] = event.get("duration_seconds", 0)
                
                snapshot_dir = Path("snapshots") / camera_id
                snapshot_dir.mkdir(parents=True, exist_ok=True)
                snapshot_path = (
                    snapshot_dir
                    / f"event_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.jpg"
                )

                # Save the frame associated with this event synchronously to avoid the race condition with Telegram sending
                frame_to_save = event.pop("custom_frame", annotated)
                cv2.imwrite(str(snapshot_path), frame_to_save, [cv2.IMWRITE_JPEG_QUALITY, 60])
                
                event["snapshot"] = str(snapshot_path)
                event["camera_id"] = camera_id
                
                if telegram and not event.get("authorized", True):
                    alert_msg = (
                        f"🚨 <b>UNAUTHORIZED ACCESS</b>\n\n"
                        f"Zone: {event['zone_name']}\n"
                        f"Camera: {camera_id.upper()}\n"
                        f"Shirt Color: {event.get('shirt_color', 'unknown').upper()}\n"
                        f"Person ID: #{event.get('track_id', '?')}\n"
                        f"Confidence: {event['confidence']*100:.1f}%\n"
                        f"Time: {event['timestamp']}"
                    )
                    dedup_key = f"{camera_id}_{event['zone_name']}_{event.get('track_id', '?')}"
                    telegram.send_alert(alert_msg, str(snapshot_path), dedup_key=dedup_key)

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
                        risk_score=event.get("risk_score", 0),
                        duration_seconds=event.get("duration_seconds", 0.0),
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
            last_annotated_frame = annotated.copy()
        else:
            if last_frame is None:
                last_annotated_frame = np.zeros((height, width, 3), dtype=np.uint8)
            else:
                last_annotated_frame = latest_frames.get(camera_id, None)
                if last_annotated_frame is None:
                    last_annotated_frame = cv2.resize(last_frame, (width, height))
                else:
                    last_annotated_frame = last_annotated_frame.copy()

        # Overlay info on frame if video is still active
        if not video_ended and not connection_lost and last_frame is not None:
            person_count = len(detections)
            info = f"Cam: {camera_id} | Persons: {person_count} | Zones: {len(zones)}"
            cv2.putText(last_annotated_frame, info, (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            if is_night_mode:
                cv2.putText(last_annotated_frame, "MODE: NIGHT PROTOCOL (IR/GRAYSCALE)", (10, 70), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 165, 255), 2)

        # Add "VIDEO ENDED" overlay if done
        if video_ended:
            cv2.putText(
                last_annotated_frame,
                "STREAM ENDED - NO ACTIVE FEED",
                (180, 216),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 0, 255),
                2,
            )

        # Encode to JPEG
        _, buffer = cv2.imencode(".jpg", last_annotated_frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
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