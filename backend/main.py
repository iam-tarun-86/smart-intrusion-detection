"""
main.py — FastAPI entry point with video streaming, REST API, and WebSocket alerts
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

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from db.database import engine, get_db
from db.models import Base, IntrusionEvent
from detection.detector import PersonDetector
from detection.zones import ZoneManager, Zone


# Create tables
Base.metadata.create_all(bind=engine)

# Global state
detector = None
zone_manager = None
video_capture = None
latest_frame = None
latest_detections = []
active_connections: List[WebSocket] = []
is_streaming = False

# Thread-safe event queue for cross-thread communication
alert_queue = Queue()
_loop = None  # Will store the event loop


def init_system():
    """Initialize detection system."""
    global detector, zone_manager
    
    detector = PersonDetector(model_name="yolov8n.pt", conf_threshold=0.5)
    zone_manager = ZoneManager()
    
    zone_manager.add_zone(Zone(
        name="Server Room",
        points=[(400, 150), (700, 150), (700, 350), (400, 350)],
        color=(0, 0, 255),
        severity="high"
    ))
    zone_manager.add_zone(Zone(
        name="Storage Area",
        points=[(50, 100), (250, 100), (250, 300), (50, 300)],
        color=(255, 165, 0),
        severity="medium"
    ))
    
    print("[System] Detection initialized")


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
    global video_capture
    if video_capture:
        video_capture.release()
        print("[System] Video capture released")


app = FastAPI(
    title="Smart Intrusion Detection API",
    description="Real-time intrusion detection with YOLOv8",
    version="1.0.0",
    lifespan=lifespan
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
        "timestamp": datetime.now().isoformat()
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
            # Use receive_text with a timeout to prevent blocking forever
            data = await asyncio.wait_for(websocket.receive_text(), timeout=60.0)
            if data == "ping":
                await websocket.send_text("pong")
    except asyncio.TimeoutError:
        # No ping received in 60s, close connection gracefully
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

def generate_frames(source_path: str = "pedestrian_test.mp4"):
    """Generator for MJPEG stream. Plays once, then holds last frame."""
    global video_capture, latest_frame, latest_detections, is_streaming
    
    cap = cv2.VideoCapture(source_path)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {source_path}")
    
    video_capture = cap
    is_streaming = True
    video_ended = False
    last_frame = None
    
    while is_streaming:
        if not video_ended:
            ret, frame = cap.read()
            if not ret:
                video_ended = True
                print("[Stream] Video ended. Holding last frame.")
            else:
                last_frame = frame.copy()
        
        # Use last good frame if video ended
        frame = last_frame.copy() if last_frame is not None else np.zeros((432, 768, 3), dtype=np.uint8)
        
        frame = cv2.resize(frame, (768, 432))
        
        # Run detection
        annotated, detections = detector.detect(frame.copy())
        
        # Check intrusions
        annotated, events = zone_manager.check_intrusion(annotated, detections)
        
        # Queue events for async processing
        for event in events:
            snapshot_dir = Path("snapshots")
            snapshot_dir.mkdir(exist_ok=True)
            snapshot_path = snapshot_dir / f"event_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.jpg"
            cv2.imwrite(str(snapshot_path), annotated)
            event["snapshot"] = str(snapshot_path)
            
            alert_queue.put(event)
            
            # Save to DB
            try:
                db = next(get_db())
                db_event = IntrusionEvent(
                    zone_name=event["zone_name"],
                    confidence=event["confidence"],
                    severity=event["severity"],
                    snapshot_path=str(snapshot_path),
                    bbox_x1=event["bbox"][0],
                    bbox_y1=event["bbox"][1],
                    bbox_x2=event["bbox"][2],
                    bbox_y2=event["bbox"][3]
                )
                db.add(db_event)
                db.commit()
                db.refresh(db_event)
                event["id"] = db_event.id
            except Exception as e:
                print(f"[DB Error] {e}")
        
        latest_frame = annotated
        latest_detections = detections
        
        # Add "VIDEO ENDED" overlay if done
        if video_ended:
            cv2.putText(annotated, "STREAM ENDED - NO ACTIVE FEED", (180, 216),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
        
        # Encode to JPEG
        _, buffer = cv2.imencode('.jpg', annotated, [cv2.IMWRITE_JPEG_QUALITY, 70])
        frame_bytes = buffer.tobytes()
        
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
    
    cap.release()

@app.get("/stream")
async def video_stream():
    """MJPEG video stream endpoint."""
    return StreamingResponse(
        generate_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


# ==================== REST API ====================

@app.get("/")
async def root():
    return {"message": "Smart Intrusion Detection API", "status": "running"}


@app.get("/alerts", response_model=List[dict])
async def get_alerts(
    limit: int = Query(50, ge=1, le=500),
    resolved: Optional[bool] = None,
    db: Session = Depends(get_db)
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
        "active_zones": list(zone_manager._active_intrusions.keys()) if zone_manager else [],
        "total_zones": len(zone_manager.zones) if zone_manager else 0,
        "streaming": is_streaming
    }


@app.get("/zones")
async def get_zones():
    """Get all configured zones."""
    if not zone_manager:
        return []
    
    return [
        {
            "name": z.name,
            "points": z.points,
            "color": z.color,
            "severity": z.severity
        }
        for z in zone_manager.zones
    ]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)