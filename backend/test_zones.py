"""
test_zones.py — Test zone-based intrusion detection
"""

import cv2
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from detection.detector import PersonDetector
from detection.zones import ZoneManager, Zone


def test_zone_detection():
    """Run detection with zone intrusion logic."""
    
    detector = PersonDetector(model_name="yolov8n.pt", conf_threshold=0.5)
    zone_manager = ZoneManager()
    
    # Define a restricted zone (adjust coordinates based on your video resolution)
    # For 768x432 video, let's define a zone in the middle-right area
    restricted_zone = Zone(
        name="Server Room",
        points=[(400, 150), (700, 150), (700, 350), (400, 350)],
        color=(0, 0, 255),
        severity="high"
    )
    zone_manager.add_zone(restricted_zone)
    
    # Add another zone on the left
    zone2 = Zone(
        name="Storage Area",
        points=[(50, 100), (250, 100), (250, 300), (50, 300)],
        color=(255, 165, 0),  # Orange
        severity="medium"
    )
    zone_manager.add_zone(zone2)
    
    # Open video
    source = "pedestrian_test.mp4"
    cap = cv2.VideoCapture(source)
    
    if not cap.isOpened():
        print(f"[Error] Cannot open {source}")
        return
    
    fps = cap.get(cv2.CAP_PROP_FPS) or 12.0
    width, height = 768, 432
    
    # Setup writer
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter("zone_detection_output.mp4", fourcc, fps, (width, height))
    
    frame_count = 0
    total_intrusions = 0
    
    print(f"[Info] Testing zone detection on {source}")
    print(f"[Info] Zones: {[z.name for z in zone_manager.zones]}")
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        
        frame_count += 1
        
        # Detect persons
        annotated_frame, detections = detector.detect(frame)
        
        # Check intrusions
        annotated_frame, events = zone_manager.check_intrusion(annotated_frame, detections)
        
        if events:
            total_intrusions += len(events)
            # Save snapshot for first event
            for event in events:
                snapshot_path = f"snapshots/intrusion_{event['timestamp'].replace(':', '-')}.jpg"
                Path(snapshot_path).parent.mkdir(parents=True, exist_ok=True)
                cv2.imwrite(snapshot_path, annotated_frame)
                event["snapshot"] = snapshot_path
        
        # Overlay stats
        stats = zone_manager.get_intrusion_stats()
        info = f"Frame: {frame_count} | Persons: {len(detections)} | Intrusions: {stats['total_intrusions']}"
        cv2.putText(annotated_frame, info, (10, 25),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        out.write(annotated_frame)
        
        if frame_count % 60 == 0:
            print(f"[Progress] Frame {frame_count} | Total intrusions: {stats['total_intrusions']}")
    
    cap.release()
    out.release()
    
    print(f"\n{'='*50}")
    print(f"[Done] Processed {frame_count} frames")
    print(f"[Done] Total intrusion events: {total_intrusions}")
    print(f"[Done] Output: zone_detection_output.mp4")
    print(f"[Done] Check 'snapshots/' folder for event images")
    print(f"{'='*50}")
    
    # Print final stats
    stats = zone_manager.get_intrusion_stats()
    print(f"\nIntrusion Log ({len(stats['events'])} recent events):")
    for event in stats['events']:
        print(f"  - {event['timestamp']} | Zone: {event['zone_name']} | Conf: {event['confidence']}")


if __name__ == "__main__":
    test_zone_detection()