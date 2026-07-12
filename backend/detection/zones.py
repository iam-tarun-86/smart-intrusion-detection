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
    
    def duration_seconds(self) -> float:
        return (datetime.now() - self.start_time).total_seconds()


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
    
    def check_intrusion(self, frame: np.ndarray, detections: List[Dict]) -> Tuple[np.ndarray, List[Dict]]:
        annotated = self.draw_zones(frame)
        new_events = []
        now = datetime.now()
        
        for detection in detections:
            bbox = detection["bbox"]
            track_id = detection.get("track_id", 0)
            person_center = self._get_bbox_center(bbox)
            x1, y1, x2, y2 = bbox
            
            # Check shirt color
            shirt_color = ColorAnalyzer.detect_shirt_color(frame, bbox)
            
            # CASE 1: Has zones — check zone-based rules
            if self.zones:
                for zone in self.zones:
                    pair_key = (zone.name, track_id)
                    is_inside = cv2.pointPolygonTest(zone.points_np, person_center, False) >= 0
                    
                    if is_inside:
                        is_authorized = shirt_color in zone.allowed_colors if zone.allowed_colors else True
                        
                        if not is_authorized:
                            cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 0, 255), 3)
                            # Debug: show detected color
                            cv2.putText(annotated, shirt_color, (x1, y2 + 18),
                                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
                            event = self._create_event(zone.name, detection, track_id, shirt_color, now)
                            if event:
                                new_events.append(event)
                        else:
                            cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)
                            # Debug: show detected color
                            cv2.putText(annotated, shirt_color, (x1, y2 + 18),
                                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
            
            # CASE 2: No zones — camera-wide uniform enforcement (SERVER ROOM MODE)
            elif self.enforce_uniform:
                # Default: check against allowed colors
                is_authorized = shirt_color in self.default_allowed
                
                if not is_authorized:
                    cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 0, 255), 3)
                    # Debug: show detected color
                    cv2.putText(annotated, shirt_color, (x1, y2 + 18),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
                    event = self._create_event(self.camera_name or "Restricted Area", 
                                              detection, track_id, shirt_color, now)
                    if event:
                        new_events.append(event)
                else:
                    cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    # Debug: show detected color
                    cv2.putText(annotated, shirt_color, (x1, y2 + 18),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
            else:
                # No zones, no uniform check — just show detection
                cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)
        
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
        # 1. Confidence score (0-30)
        conf = detection.get("confidence", 0)
        confidence_score = min(int(conf * 30), 30)
        
        # 2. Duration score (0-30) — longer = higher risk
        # Cap at 60 seconds for max score
        duration_score = min(int((duration / 60) * 30), 30)
        
        # 3. Zone sensitivity (0-20)
        zone_sensitivity = {
            "Server Room": 20,
            "server room": 20,
            "Restricted Area": 18,
            "Storage Area": 12,
            "Parking Lot": 8,
            "parking lot": 8,
        }
        sensitivity_score = zone_sensitivity.get(zone_name, 10)
        
        # 4. Uniform violation (0-20)
        violation_score = 0
        if shirt_color and shirt_color not in ["blue", "white", "unknown"]:
            violation_score = 20  # Strong violation
        elif shirt_color == "unknown":
            violation_score = 10  # Ambiguous
        
        total = confidence_score + duration_score + sensitivity_score + violation_score
        return min(total, 100)

    def _create_event(self, zone_name: str, detection: Dict, track_id: int, 
                      shirt_color: str, now: datetime) -> Optional[Dict]:
        """Create alert event with cooldown and risk score."""
        pair_key = (zone_name, track_id)
        
        if pair_key in self._active_intrusions:
            last_alert = self._active_intrusions[pair_key].last_alert_time
            seconds_since = (now - last_alert).total_seconds()
            if seconds_since < self.ALERT_COOLDOWN_SECONDS:
                return None
        
        # Calculate duration
        duration = 0
        if pair_key in self._active_intrusions:
            duration = self._active_intrusions[pair_key].duration_seconds()
        
        # Calculate risk score
        risk_score = self._calculate_risk_score(detection, duration, zone_name, shirt_color)
        
        if pair_key not in self._active_intrusions:
            self._active_intrusions[pair_key] = IntrusionState(
                zone_name=zone_name,
                track_id=track_id,
                person_center=self._get_bbox_center(detection["bbox"]),
                start_time=now,
                last_alert_time=now,
                frame_count=1,
                consecutive_frames=1
            )
        else:
            self._active_intrusions[pair_key].last_alert_time = now
        
        event = {
            "timestamp": now.isoformat(),
            "zone_name": zone_name,
            "severity": "high",
            "confidence": detection["confidence"],
            "bbox": detection["bbox"],
            "track_id": track_id,
            "shirt_color": shirt_color,
            "authorized": False,
            "risk_score": risk_score,  # NEW
            "duration_seconds": round(duration, 1),  # NEW
            "snapshot": None
        }
        self.intrusion_log.append(event)
        print(f"[ALERT] 🚨 Risk:{risk_score} | {shirt_color.upper()} SHIRT in '{zone_name}'! ID:{track_id}")
        return event
    
    def reset_alerts(self):
        """Reset only cleared tracks, keep active ones."""
        # Only remove tracks that are no longer active
        cleared = [k for k, v in self._active_intrusions.items() 
                   if not v.is_active]
        for k in cleared:
            del self._active_intrusions[k]
    
    @staticmethod
    def _get_centroid(points: List[Tuple[int, int]]) -> Tuple[int, int]:
        x_coords = [p[0] for p in points]
        y_coords = [p[1] for p in points]
        return (int(sum(x_coords) / len(x_coords)), int(sum(y_coords) / len(y_coords)))
    
    @staticmethod
    def _get_bbox_center(bbox: Tuple[int, int, int, int]) -> Tuple[int, int]:
        x1, y1, x2, y2 = bbox
        return (int((x1 + x2) / 2), int((y1 + y2) / 2))