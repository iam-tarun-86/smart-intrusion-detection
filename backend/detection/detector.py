"""
detector.py — YOLOv8 Person Detection Module
"""

import cv2
from ultralytics import YOLO
from pathlib import Path


class PersonDetector:
    def __init__(self, model_name: str = "yolov8n.pt", conf_threshold: float = 0.5):
        """
        Initialize YOLOv8 model for person detection.
        
        Args:
            model_name: YOLOv8 model variant (yolov8n.pt, yolov8s.pt, etc.)
            conf_threshold: Minimum confidence score for detection
        """
        self.model = YOLO(model_name)
        self.conf_threshold = conf_threshold
        self.person_class_id = 0  # COCO: 0 = person
        
        print(f"[Detector] Loaded {model_name} | Conf threshold: {conf_threshold}")

    def detect(self, frame):
        """
        Run detection on a single frame.
        
        Args:
            frame: OpenCV BGR image (numpy array)
            
        Returns:
            annotated_frame: Frame with bounding boxes drawn
            detections: List of dicts with bbox, confidence for persons only
        """
        results = self.model(frame, verbose=False)
        detections = []
        
        # Get the first result (single image)
        result = results[0]
        
        # Extract person detections
        for box in result.boxes:
            cls_id = int(box.cls[0])
            conf = float(box.conf[0])
            
            if cls_id == self.person_class_id and conf >= self.conf_threshold:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                detections.append({
                    "bbox": (x1, y1, x2, y2),
                    "confidence": round(conf, 3)
                })
                
                # Draw bounding box
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                label = f"Person {conf:.2f}"
                cv2.putText(frame, label, (x1, y1 - 10),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        
        return frame, detections

    def get_person_count(self, detections: list) -> int:
        """Return number of persons detected."""
        return len(detections)