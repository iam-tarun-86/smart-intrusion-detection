"""
detector.py — YOLOv8 Person Detection + ByteTrack Module
"""

import cv2
from ultralytics import YOLO
from pathlib import Path
from typing import List, Dict, Tuple
import numpy as np


class ByteTrack:
    """
    Simple IoU-based tracker. Assigns persistent IDs to detections across frames.
    """
    def __init__(self, max_age: int = 30, min_hits: int = 3, iou_threshold: float = 0.3):
        self.max_age = max_age          # Frames to keep lost tracks
        self.min_hits = min_hits        # Min frames before track is confirmed
        self.iou_threshold = iou_threshold
        
        self.tracks: Dict[int, Dict] = {}  # track_id -> {bbox, age, hits, last_seen}
        self.next_id = 1
        self.frame_count = 0

    def _iou(self, boxA: Tuple, boxB: Tuple) -> float:
        """Calculate Intersection over Union of two bounding boxes."""
        xA = max(boxA[0], boxB[0])
        yA = max(boxA[1], boxB[1])
        xB = min(boxA[2], boxB[2])
        yB = min(boxA[3], boxB[3])
        
        interW = max(0, xB - xA)
        interH = max(0, yB - yA)
        interArea = interW * interH
        
        boxAArea = (boxA[2] - boxA[0]) * (boxA[3] - boxA[1])
        boxBArea = (boxB[2] - boxB[0]) * (boxB[3] - boxB[1])
        
        unionArea = boxAArea + boxBArea - interArea
        return interArea / unionArea if unionArea > 0 else 0

    def update(self, detections: List[Dict]) -> List[Dict]:
        """
        Match current detections to existing tracks.
        Returns detections with added 'track_id' field.
        """
        self.frame_count += 1
        
        # Mark all tracks as not updated this frame
        for track_id in self.tracks:
            self.tracks[track_id]['updated'] = False
        
        # Match detections to tracks
        matched_tracks = set()
        matched_dets = set()
        
        # Sort tracks by age (prefer older tracks)
        track_ids = sorted(self.tracks.keys(), 
                          key=lambda tid: self.tracks[tid]['age'])
        
        for track_id in track_ids:
            track_bbox = self.tracks[track_id]['bbox']
            best_iou = self.iou_threshold
            best_det_idx = -1
            
            for i, det in enumerate(detections):
                if i in matched_dets:
                    continue
                    
                iou = self._iou(track_bbox, det['bbox'])
                if iou > best_iou:
                    best_iou = iou
                    best_det_idx = i
            
            if best_det_idx >= 0:
                # Match found
                self.tracks[track_id]['bbox'] = detections[best_det_idx]['bbox']
                self.tracks[track_id]['age'] += 1
                self.tracks[track_id]['hits'] += 1
                self.tracks[track_id]['updated'] = True
                self.tracks[track_id]['lost'] = 0
                matched_tracks.add(track_id)
                matched_dets.add(best_det_idx)
                detections[best_det_idx]['track_id'] = track_id
        
        # Create new tracks for unmatched detections
        for i, det in enumerate(detections):
            if i not in matched_dets:
                new_id = self.next_id
                self.next_id += 1
                self.tracks[new_id] = {
                    'bbox': det['bbox'],
                    'age': 1,
                    'hits': 1,
                    'updated': True,
                    'lost': 0
                }
                det['track_id'] = new_id
        
        # Age out lost tracks
        lost_tracks = []
        for track_id in list(self.tracks.keys()):
            if not self.tracks[track_id]['updated']:
                self.tracks[track_id]['lost'] += 1
                if self.tracks[track_id]['lost'] > self.max_age:
                    lost_tracks.append(track_id)
        
        for track_id in lost_tracks:
            del self.tracks[track_id]
        
        # Only return confirmed tracks (min_hits) or currently visible
        for det in detections:
            tid = det.get('track_id')
            if tid and self.tracks[tid]['hits'] < self.min_hits and self.tracks[tid]['lost'] == 0:
                # Tentative track — still assign ID but mark as tentative
                det['track_confirmed'] = False
            else:
                det['track_confirmed'] = True
        
        return detections

    def get_track_age(self, track_id: int) -> int:
        """Get how many frames this track has existed."""
        if track_id in self.tracks:
            return self.tracks[track_id]['age']
        return 0


class PersonDetector:
    def __init__(self, model_name: str = "yolov8n.pt", conf_threshold: float = 0.5):
        self.model = YOLO(model_name)
        self.conf_threshold = conf_threshold
        self.person_class_id = 0
        self.tracker = ByteTrack(max_age=30, min_hits=3, iou_threshold=0.3)
        
        print(f"[Detector] Loaded {model_name} | Conf: {conf_threshold} | ByteTrack enabled")

    def detect(self, frame):
        """
        Run detection + tracking on a single frame.
        
        Returns:
            annotated_frame: Frame with boxes and track IDs drawn
            detections: List of dicts with bbox, confidence, track_id, track_confirmed
        """
        results = self.model(frame, verbose=False)
        detections = []
        
        result = results[0]
        
        for box in result.boxes:
            cls_id = int(box.cls[0])
            conf = float(box.conf[0])
            
            if cls_id == self.person_class_id and conf >= self.conf_threshold:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                detections.append({
                    "bbox": (x1, y1, x2, y2),
                    "confidence": round(conf, 3)
                })
        
        # Apply tracking
        detections = self.tracker.update(detections)
        
        # Draw boxes — green for normal, yellow for tentative, red handled by zones.py
        for det in detections:
            x1, y1, x2, y2 = det['bbox']
            confirmed = det.get('track_confirmed', False)
            color = (0, 255, 0) if confirmed else (0, 255, 255)
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        
        return frame, detections

    def get_person_count(self, detections: list) -> int:
        return len(detections)