"""
test_detection.py — Headless YOLOv8 Person Detection
Saves output video + prints detection stats. No GUI required.
"""

import cv2
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from detection.detector import PersonDetector


def run_detection_headless(source: str, output_path: str = "output_detected.mp4", display_size=(1280, 720)):
    """
    Run detection and save output video. No GUI window.
    
    Args:
        source: Path to input video file
        output_path: Path to save annotated output video
        display_size: (width, height) for processing
    """
    detector = PersonDetector(model_name="yolov8n.pt", conf_threshold=0.5)
    
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        print(f"[Error] Cannot open video source: {source}")
        return
    
    # Get video properties
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    print(f"[Info] Video: {width}x{height} @ {fps:.1f}fps | Frames: {total_frames}")
    print(f"[Info] Output will be saved to: {output_path}")
    
    # Setup video writer
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, display_size)
    
    frame_count = 0
    processed = 0
    start_time = time.time()
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        
        frame_count += 1
        
        # Resize for consistent processing
        frame = cv2.resize(frame, display_size)
        
        # Run detection every frame (we'll optimize to every N frames later)
        annotated_frame, detections = detector.detect(frame)
        
        # Overlay info
        person_count = detector.get_person_count(detections)
        info_text = f"Frame: {frame_count} | Persons: {person_count}"
        cv2.putText(annotated_frame, info_text, (10, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
        
        # Write to output
        out.write(annotated_frame)
        processed += 1
        
        # Progress every 30 frames
        if frame_count % 30 == 0:
            elapsed = time.time() - start_time
            current_fps = processed / elapsed
            print(f"[Progress] Frame {frame_count}/{total_frames} | "
                  f"FPS: {current_fps:.1f} | Persons this frame: {person_count}")
    
    # Cleanup
    cap.release()
    out.release()
    
    elapsed = time.time() - start_time
    print(f"\n{'='*50}")
    print(f"[Done] Processed {processed} frames in {elapsed:.1f}s")
    print(f"[Done] Average FPS: {processed/elapsed:.1f}")
    print(f"[Done] Output saved: {output_path}")
    print(f"{'='*50}")
    
    return output_path


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Headless YOLOv8 Person Detection")
    parser.add_argument("--source", type=str, required=True,
                       help="Path to input video file")
    parser.add_argument("--output", type=str, default="output_detected.mp4",
                       help="Path to save output video")
    parser.add_argument("--width", type=int, default=1280, help="Output width")
    parser.add_argument("--height", type=int, default=720, help="Output height")
    
    args = parser.parse_args()
    
    run_detection_headless(
        source=args.source,
        output_path=args.output,
        display_size=(args.width, args.height)
    )