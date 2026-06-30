"""
stream_manager.py — Handles multiple video streams
"""

import cv2
import json
import shutil
from pathlib import Path
from typing import Dict, Optional
from dataclasses import dataclass, asdict


@dataclass
class CameraConfig:
    id: str
    name: str
    source: str
    enabled: bool = True


class StreamManager:
    """Manages multiple video streams with per-camera zone configs."""

    CONFIG_FILE = Path("cameras.json")

    def __init__(self):
        self.cameras: Dict[str, CameraConfig] = {}
        self.captures: Dict[str, cv2.VideoCapture] = {}
        self._load_config()

    def _load_config(self):
        """Load camera configurations from JSON."""
        if self.CONFIG_FILE.exists():
            with open(self.CONFIG_FILE) as f:
                data = json.load(f)
                for cam in data.get("cameras", []):
                    self.cameras[cam["id"]] = CameraConfig(**cam)
            print(f"[StreamManager] Loaded {len(self.cameras)} cameras")
        else:
            # Default: single test video
            self.cameras["cam1"] = CameraConfig(
                id="cam1",
                name="Main Entrance",
                source="pedestrian_test.mp4"
            )
            self._save_config()

    def _save_config(self):
        """Save camera configurations to JSON."""
        data = {"cameras": [asdict(cam) for cam in self.cameras.values()]}
        with open(self.CONFIG_FILE, "w") as f:
            json.dump(data, f, indent=2)

    def get_capture(self, camera_id: str) -> Optional[cv2.VideoCapture]:
        """Get or create VideoCapture for a camera."""
        if camera_id not in self.cameras:
            return None

        # Return existing if still open
        if camera_id in self.captures:
            cap = self.captures[camera_id]
            if cap.isOpened():
                return cap
            cap.release()

        # Create new capture
        config = self.cameras[camera_id]
        source = int(config.source) if config.source.isdigit() else config.source

        cap = cv2.VideoCapture(source)
        if cap.isOpened():
            self.captures[camera_id] = cap
            print(f"[StreamManager] Opened camera: {config.name} ({camera_id})")
            return cap

        print(f"[StreamManager] Failed to open: {config.source}")
        return None

    def list_cameras(self):
        """Return list of camera configs."""
        return [
            {
                "id": cam.id,
                "name": cam.name,
                "enabled": cam.enabled,
                "source": cam.source,
            }
            for cam in self.cameras.values()
        ]

    def add_camera(self, config: CameraConfig):
        """Add a new camera."""
        self.cameras[config.id] = config
        self._save_config()

    def release_all(self):
        """Release all captures."""
        for cap in self.captures.values():
            cap.release()
        self.captures.clear()


def setup_test_cameras():
    """Create test camera configs with copies of the same video."""
    # Copy video for cam2 if not exists
    if not Path("pedestrian_test2.mp4").exists():
        shutil.copy("pedestrian_test.mp4", "pedestrian_test2.mp4")

    manager = StreamManager()

    # Add second camera if not exists
    if "cam2" not in manager.cameras:
        manager.add_camera(
            CameraConfig(
                id="cam2",
                name="Side Gate",
                source="pedestrian_test2.mp4",
            )
        )

    return manager