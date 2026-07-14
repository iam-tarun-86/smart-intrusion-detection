"""
zones.py — Zone-based + Camera-wide Intrusion Detection
"""

import cv2
import numpy as np
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from detection.color_analyzer import ColorAnalyzer


@dataclass
class Zone:
    """Represents a restricted zone as a polygon."""
    name: str
    points: List[Tuple[int, int]]
    color: Tuple[int, int, int] = (0, 0, 255)
    severity: str = "high"
    allowed_colors: List[str] = None
    
    def __post_init__(self):
        self.points_np = np.array(self.points, np.int32)
        self.points_np = self.points_np.reshape((-1, 1, 2))
        if self.allowed_colors is None:
            self.allowed_colors = []


@dataclass
class IntrusionState:
    """Tracks active intrusion state for a specific person."""
    zone_name: str
    track_id: int
    person_center: Tuple[int, int]
    start_time: datetime
    last_alert_time: datetime
    frame_count: int = 0
    consecutive_frames: int = 0
    is_active: bool = True
    
    # Perfect shot tracking
    best_score: float = -1.0
    best_frame: Optional[np.ndarray] = None
    best_bbox: Tuple[int, int, int, int] = (0, 0, 0, 0)
    best_confidence: float = 0.0
    best_shirt_color: str = "unknown"
    alert_triggered: bool = False
    
    def duration_seconds(self) -> float:
        return (datetime.now() - self.start_time).total_seconds()

    def update_best_frame(self, frame: np.ndarray, bbox: Tuple[int, int, int, int], confidence: float, shirt_color: str):
        x1, y1, x2, y2 = bbox
        h, w = frame.shape[:2]
        
        # Penalize bounding boxes that are too close to the borders of the image (cut-off)
        margin = 20
        touching_edge = (x1 < margin) or (y1 < margin) or (x2 > w - margin) or (y2 > h - margin)
        
        # Bounding box area
        area = (x2 - x1) * (y2 - y1)
        
        # Quality score = confidence * area (larger and higher confidence is better)
        score = confidence * area
        if touching_edge:
            score *= 0.1  # Heavily penalize cut-off frames
            
        if score > self.best_score or self.best_frame is None:
            self.best_score = score
            self.best_frame = frame.copy()
            self.best_bbox = bbox
            self.best_confidence = confidence
            self.best_shirt_color = shirt_color


class ZoneManager:
    """Manages zones with optional camera-wide intrusion detection."""
    
    ALERT_COOLDOWN_SECONDS = 10  # Shorter for demo
    
    def __init__(self, camera_name: str = "", enforce_uniform: bool = True, default_allowed: list = None):
        self.zones: List[Zone] = []
        self.camera_name = camera_name
        self.enforce_uniform = enforce_uniform  # If True, check shirt colors
        self.default_allowed = default_allowed or ["blue"]  # Fallback
        self.intrusion_log: List[Dict] = []
        self._active_intrusions: Dict[Tuple[str, int], IntrusionState] = {}
        self._alerted_tracks: set = set()  # Tracks already alerted this session
        
    def add_zone(self, zone: Zone):
        self.zones.append(zone)
        print(f"[ZoneManager] Added zone '{zone.name}'")
        
    def load_from_config(self, config: List[Dict]):
        for item in config:
            zone = Zone(
                name=item["name"],
                points=[tuple(p) for p in item["points"]],
                color=tuple(item.get("color", [0, 0, 255])),
                severity=item.get("severity", "high"),
                allowed_colors=item.get("allowed_colors", [])
            )
            self.add_zone(zone)
            
    def draw_zones(self, frame: np.ndarray) -> np.ndarray:
        annotated = frame.copy()
        for zone in self.zones:
            cv2.polylines(annotated, [zone.points_np], True, zone.color, 2)
            centroid = self._get_centroid(zone.points)
            cv2.putText(annotated, f"ZONE: {zone.name}", centroid,
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, zone.color, 2)
        return annotated

    @staticmethod
    def check_is_night_mode(frame: np.ndarray) -> bool:
        """Analyze average saturation to detect IR/Grayscale Night Mode."""
        if frame is None or frame.size == 0:
            return False
        # Resize to small size for faster processing
        small = cv2.resize(frame, (100, 100))
        hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
        avg_s = np.mean(hsv[:, :, 1])
        # IR cameras or low light grayscale streams have extremely low saturation (usually S < 15)
        return bool(avg_s < 15)

    def check_intrusion(self, frame: np.ndarray, detections: List[Dict], is_night_mode: bool = False) -> Tuple[np.ndarray, List[Dict]]:
        annotated = self.draw_zones(frame)
        new_events = []
        now = datetime.now()
        
        # Mark all active intrusions as not seen in this frame initially
        for state in self._active_intrusions.values():
            state.is_active = False
            
        for detection in detections:
            bbox = detection["bbox"]
            track_id = detection.get("track_id", 0)
            person_center = self._get_bbox_center(bbox)
            x1, y1, x2, y2 = bbox
            
            # Check shirt color (override if night mode is active)
            shirt_color = "night-ir" if is_night_mode else ColorAnalyzer.detect_shirt_color(frame, bbox)
            
            # CASE 1: Has zones — check zone-based rules
            if self.zones:
                for zone in self.zones:
                    pair_key = (zone.name, track_id)
                    is_inside = cv2.pointPolygonTest(zone.points_np, person_center, False) >= 0
                    
                    if is_inside:
                        is_authorized = False if is_night_mode else (shirt_color in zone.allowed_colors if zone.allowed_colors else True)
                        
                        if not is_authorized:
                            cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 0, 255), 3)
                            cv2.putText(annotated, shirt_color.upper(), (x1, y2 + 18),
                                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
                            
                            if pair_key not in self._active_intrusions:
                                self._active_intrusions[pair_key] = IntrusionState(
                                    zone_name=zone.name,
                                    track_id=track_id,
                                    person_center=person_center,
                                    start_time=now,
                                    last_alert_time=now
                                )
                            
                            state = self._active_intrusions[pair_key]
                            state.is_active = True
                            state.frame_count += 1
                            state.update_best_frame(frame, bbox, detection["confidence"], shirt_color)
                            
                            # Check cooldown reset
                            seconds_since = (now - state.last_alert_time).total_seconds()
                            if state.alert_triggered and seconds_since >= self.ALERT_COOLDOWN_SECONDS:
                                state.alert_triggered = False
                                state.best_score = -1.0
                                state.best_frame = None
                                
                            # Alert if we have enough frames to get a good shot
                            if not state.alert_triggered and state.frame_count >= 8:
                                state.alert_triggered = True
                                state.last_alert_time = now
                                event = self._create_event_from_state(state, zone.severity, zone.allowed_colors, now)
                                new_events.append(event)
                        else:
                            cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)
                            cv2.putText(annotated, shirt_color.upper(), (x1, y2 + 18),
                                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
            
            # CASE 2: No zones — camera-wide uniform enforcement
            elif self.enforce_uniform:
                is_authorized = False if is_night_mode else (shirt_color in self.default_allowed)
                
                if not is_authorized:
                    cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 0, 255), 3)
                    cv2.putText(annotated, shirt_color.upper(), (x1, y2 + 18),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
                    
                    zone_name = self.camera_name or "Restricted Area"
                    pair_key = (zone_name, track_id)
                    if pair_key not in self._active_intrusions:
                        self._active_intrusions[pair_key] = IntrusionState(
                            zone_name=zone_name,
                            track_id=track_id,
                            person_center=person_center,
                            start_time=now,
                            last_alert_time=now
                        )
                    
                    state = self._active_intrusions[pair_key]
                    state.is_active = True
                    state.frame_count += 1
                    state.update_best_frame(frame, bbox, detection["confidence"], shirt_color)
                    
                    seconds_since = (now - state.last_alert_time).total_seconds()
                    if state.alert_triggered and seconds_since >= self.ALERT_COOLDOWN_SECONDS:
                        state.alert_triggered = False
                        state.best_score = -1.0
                        state.best_frame = None
                        
                    if not state.alert_triggered and state.frame_count >= 8:
                        state.alert_triggered = True
                        state.last_alert_time = now
                        event = self._create_event_from_state(state, "high", self.default_allowed, now)
                        new_events.append(event)
                else:
                    cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    cv2.putText(annotated, shirt_color.upper(), (x1, y2 + 18),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
            else:
                cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)
        
        # Check for inactive tracks that left the zone before the alert could be triggered
        for pair_key, state in list(self._active_intrusions.items()):
            if not state.is_active:
                if not state.alert_triggered:
                    state.alert_triggered = True
                    state.last_alert_time = now
                    event = self._create_event_from_state(state, "high", [], now)
                    new_events.append(event)
                
                # Clear active intrusions if they leave and their cooldown has expired
                seconds_since_last_alert = (now - state.last_alert_time).total_seconds()
                if seconds_since_last_alert >= self.ALERT_COOLDOWN_SECONDS:
                    del self._active_intrusions[pair_key]
                    
        return annotated, new_events

    def _calculate_risk_score(self, detection: Dict, duration: float, 
                              zone_name: str, shirt_color: str) -> int:
        """
        Calculate 0-100 risk score based on:
        - Confidence: 0-30 points
        - Duration in zone: 0-30 points  
        - Zone sensitivity: 0-20 points
        - Uniform violation: 0-20 points
        """
        conf = detection.get("confidence", 0)
        confidence_score = min(int(conf * 30), 30)
        
        duration_score = min(int((duration / 60) * 30), 30)
        
        zone_sensitivity = {
            "Server Room": 20,
            "server room": 20,
            "Restricted Area": 18,
            "Storage Area": 12,
            "Parking Lot": 8,
            "parking lot": 8,
        }
        sensitivity_score = zone_sensitivity.get(zone_name, 10)
        
        violation_score = 0
        if shirt_color == "night-ir":
            violation_score = 20
        elif shirt_color and shirt_color not in ["blue", "white", "unknown"]:
            violation_score = 20
        elif shirt_color == "unknown":
            violation_score = 10
            
        total = confidence_score + duration_score + sensitivity_score + violation_score
        return min(total, 100)

    def _create_event_from_state(self, state: IntrusionState, severity: str, allowed_colors: list, now: datetime) -> Dict:
        annotated_best = state.best_frame.copy() if state.best_frame is not None else np.zeros((432, 768, 3), dtype=np.uint8)
        
        for zone in self.zones:
            cv2.polylines(annotated_best, [zone.points_np], True, zone.color, 2)
            centroid = self._get_centroid(zone.points)
            cv2.putText(annotated_best, f"ZONE: {zone.name}", centroid,
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, zone.color, 2)
                       
        x1, y1, x2, y2 = state.best_bbox
        cv2.rectangle(annotated_best, (x1, y1), (x2, y2), (0, 0, 255), 3)
        cv2.putText(annotated_best, f"ID:{state.track_id} {state.best_shirt_color}", (x1, y2 + 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
                    
        duration = state.duration_seconds()
        risk_score = self._calculate_risk_score(
            {"confidence": state.best_confidence}, duration, state.zone_name, state.best_shirt_color
        )
        
        event = {
            "timestamp": now.isoformat(),
            "zone_name": state.zone_name,
            "severity": severity,
            "confidence": state.best_confidence,
            "bbox": list(state.best_bbox),
            "track_id": state.track_id,
            "shirt_color": state.best_shirt_color,
            "authorized": False,
            "risk_score": risk_score,
            "duration_seconds": round(duration, 1),
            "snapshot": None,
            "custom_frame": annotated_best
        }
        self.intrusion_log.append(event)
        print(f"[ALERT] 🚨 Perfect Shot Risk:{risk_score} | {state.best_shirt_color.upper()} SHIRT in '{state.zone_name}'! ID:{state.track_id}")
        return event
    
    def reset_alerts(self):
        """Force reset all tracked alerts (e.g. when video loops or manually triggered)."""
        self._active_intrusions.clear()
    
    @staticmethod
    def _get_centroid(points: List[Tuple[int, int]]) -> Tuple[int, int]:
        x_coords = [p[0] for p in points]
        y_coords = [p[1] for p in points]
        return (int(sum(x_coords) / len(x_coords)), int(sum(y_coords) / len(y_coords)))
    
    @staticmethod
    def _get_bbox_center(bbox: Tuple[int, int, int, int]) -> Tuple[int, int]:
        x1, y1, x2, y2 = bbox
        return (int((x1 + x2) / 2), int((y1 + y2) / 2))