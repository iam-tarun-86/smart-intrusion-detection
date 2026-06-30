"""
zones.py — Restricted Zone Definition & Intrusion Detection Logic
"""

import cv2
import numpy as np
from typing import List, Dict, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass
class Zone:
    """Represents a restricted zone as a polygon."""
    name: str
    points: List[Tuple[int, int]]
    color: Tuple[int, int, int] = (0, 0, 255)
    severity: str = "high"
    
    def __post_init__(self):
        self.points_np = np.array(self.points, np.int32)
        self.points_np = self.points_np.reshape((-1, 1, 2))


@dataclass
class IntrusionState:
    """Tracks active intrusion state for a zone."""
    zone_name: str
    person_center: Tuple[int, int]
    start_time: datetime
    last_alert_time: datetime
    is_active: bool = True
    frame_count: int = 0  # Consecutive frames inside


class ZoneManager:
    """Manages multiple restricted zones and intrusion detection."""
    
    ALERT_COOLDOWN_SECONDS = 30
    MIN_PERSISTENCE_FRAMES = 5  # Must be inside for 3+ frames to trigger
    CLEAR_GRACE_FRAMES = 10     # Must be outside for 5+ frames to clear
    
    def __init__(self):
        self.zones: List[Zone] = []
        self.intrusion_log: List[Dict] = []
        self._active_intrusions: Dict[str, IntrusionState] = {}
        self._zone_frame_counters: Dict[str, int] = {}  # Frames since last seen inside
        
    def add_zone(self, zone: Zone):
        self.zones.append(zone)
        print(f"[ZoneManager] Added zone '{zone.name}' with {len(zone.points)} points")
        
    def load_from_config(self, config: List[Dict]):
        for item in config:
            zone = Zone(
                name=item["name"],
                points=[tuple(p) for p in item["points"]],
                color=tuple(item.get("color", [0, 0, 255])),
                severity=item.get("severity", "high")
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
        
        # Track which zones currently have confirmed intruders
        zones_with_intruders = set()
        
        for detection in detections:
            bbox = detection["bbox"]
            person_center = self._get_bbox_center(bbox)
            
            for zone in self.zones:
                is_inside = cv2.pointPolygonTest(zone.points_np, person_center, False) >= 0
                
                if is_inside:
                    zones_with_intruders.add(zone.name)
                    
                    # Draw intruder highlight
                    x1, y1, x2, y2 = bbox
                    cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 0, 255), 3)
                    cv2.putText(annotated, "INTRUDER!", (x1, y1 - 10),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
                    
                    # Manage persistence counter
                    if zone.name not in self._zone_frame_counters:
                        self._zone_frame_counters[zone.name] = 0
                    self._zone_frame_counters[zone.name] += 1
                    
                    # Only alert after minimum persistence
                    if self._zone_frame_counters[zone.name] >= self.MIN_PERSISTENCE_FRAMES:
                        should_alert = self._should_alert(zone.name, person_center, now)
                        
                        if should_alert:
                            event = {
                                "timestamp": now.isoformat(),
                                "zone_name": zone.name,
                                "severity": zone.severity,
                                "confidence": detection["confidence"],
                                "bbox": bbox,
                                "snapshot": None
                            }
                            new_events.append(event)
                            self.intrusion_log.append(event)
                            
                            self._active_intrusions[zone.name] = IntrusionState(
                                zone_name=zone.name,
                                person_center=person_center,
                                start_time=now,
                                last_alert_time=now,
                                is_active=True,
                                frame_count=self._zone_frame_counters[zone.name]
                            )
                            print(f"[ALERT] 🚨 Intrusion in '{zone.name}'! "
                                  f"Conf: {detection['confidence']:.3f} "
                                  f"(persisted {self._zone_frame_counters[zone.name]} frames)")
                else:
                    # Person not in this zone — decrement counter
                    if zone.name in self._zone_frame_counters:
                        self._zone_frame_counters[zone.name] = max(0, self._zone_frame_counters[zone.name] - 1)
        
        # Check for cleared zones (grace period)
        cleared_zones = []
        for zone_name in list(self._active_intrusions.keys()):
            if zone_name not in zones_with_intruders:
                # Check if counter dropped below threshold for enough time
                counter = self._zone_frame_counters.get(zone_name, 0)
                if counter < self.MIN_PERSISTENCE_FRAMES:
                    cleared_zones.append(zone_name)
        
        for zone_name in cleared_zones:
            if zone_name in self._active_intrusions:
                del self._active_intrusions[zone_name]
                if zone_name in self._zone_frame_counters:
                    del self._zone_frame_counters[zone_name]
                print(f"[CLEARED] Zone '{zone_name}' is now clear")
                        
        return annotated, new_events
    
    def _should_alert(self, zone_name: str, person_center: Tuple[int, int], now: datetime) -> bool:
        if zone_name not in self._active_intrusions:
            return True
        
        state = self._active_intrusions[zone_name]
        if not state.is_active:
            return True
        
        time_since_last = (now - state.last_alert_time).total_seconds()
        if time_since_last >= self.ALERT_COOLDOWN_SECONDS:
            state.last_alert_time = now
            return True
        
        return False
    
    def get_intrusion_stats(self) -> Dict:
        return {
            "total_zones": len(self.zones),
            "total_intrusions": len(self.intrusion_log),
            "active_zones": list(self._active_intrusions.keys()),
            "events": self.intrusion_log[-10:]
        }
    
    @staticmethod
    def _get_centroid(points: List[Tuple[int, int]]) -> Tuple[int, int]:
        x_coords = [p[0] for p in points]
        y_coords = [p[1] for p in points]
        return (int(sum(x_coords) / len(x_coords)), int(sum(y_coords) / len(y_coords)))
    
    @staticmethod
    def _get_bbox_center(bbox: Tuple[int, int, int, int]) -> Tuple[int, int]:
        x1, y1, x2, y2 = bbox
        return (int((x1 + x2) / 2), int((y1 + y2) / 2))