"""
color_analyzer.py — Detect dominant shirt color from person crop
"""

import cv2
import numpy as np
from typing import Tuple, List


class ColorAnalyzer:
    """Analyzes shirt color from a person bounding box."""
    
    # HSV ranges — wider for white, tighter for black
    COLOR_RANGES = {
        "blue": ((100, 60, 60), (130, 255, 255)),
        "white": ((0, 0, 140), (180, 60, 255)),      # Very wide for white/light
        "red": ((0, 60, 60), (10, 255, 255)),
        "green": ((40, 60, 60), (80, 255, 255)),
        "black": ((0, 0, 0), (180, 80, 60)),         # Very tight — must be dark
        "yellow": ((20, 60, 60), (35, 255, 255)),
        "orange": ((10, 60, 60), (25, 255, 255)),
    }
    
    @staticmethod
    def detect_shirt_color(frame: np.ndarray, bbox: Tuple[int, int, int, int]) -> str:
        x1, y1, x2, y2 = bbox
        h, w = frame.shape[:2]
        
        # Crop chest area (avoid face at top, avoid pants at bottom)
        shirt_y1 = y1 + int((y2 - y1) * 0.2)
        shirt_y2 = y1 + int((y2 - y1) * 0.55)
        shirt_x1 = max(0, x1 + int((x2 - x1) * 0.15))
        shirt_x2 = min(w, x2 - int((x2 - x1) * 0.15))
        shirt_y1 = max(0, shirt_y1)
        shirt_y2 = min(h, shirt_y2)
        
        if shirt_x2 <= shirt_x1 or shirt_y2 <= shirt_y1:
            return "unknown"
        
        shirt_region = frame[shirt_y1:shirt_y2, shirt_x1:shirt_x2]
        if shirt_region.size == 0:
            return "unknown"
        
        hsv = cv2.cvtColor(shirt_region, cv2.COLOR_BGR2HSV)
        
        # Get average HSV values
        avg_h = np.mean(hsv[:, :, 0])
        avg_s = np.mean(hsv[:, :, 1])
        avg_v = np.mean(hsv[:, :, 2])
        
        # ===== BRIGHTNESS-BASED FAST CHECKS =====
        
        # Very bright + low saturation = white (parking lot lights make shirts bright)
        if avg_v > 160 and avg_s < 70:
            return "white"
        
        # Very dark = black
        if avg_v < 50:
            return "black"
        
        # Dark gray zone — could be black or dark clothes
        if avg_v < 90 and avg_s < 40:
            return "black"
        
        # ===== MASK MATCHING FOR COLORS =====
        
        best_color = "unknown"
        best_count = 0
        
        for color_name, (lower, upper) in ColorAnalyzer.COLOR_RANGES.items():
            lower = np.array(lower)
            upper = np.array(upper)
            
            if color_name == "red":
                mask1 = cv2.inRange(hsv, lower, upper)
                mask2 = cv2.inRange(hsv, np.array([170, 60, 60]), np.array([180, 255, 255]))
                mask = cv2.bitwise_or(mask1, mask2)
            else:
                mask = cv2.inRange(hsv, lower, upper)
            
            count = cv2.countNonZero(mask)
            if count > best_count:
                best_count = count
                best_color = color_name
        
        # If mask matching is weak, fall back to brightness
        total_pixels = shirt_region.shape[0] * shirt_region.shape[1]
        match_ratio = best_count / total_pixels
        
        if match_ratio < 0.10:
            if avg_v > 130:
                return "white"
            elif avg_v < 70:
                return "black"
            else:
                return "unknown"
        
        return best_color