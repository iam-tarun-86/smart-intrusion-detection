"""
zone_config.py — Save/load zone configurations per camera
"""

import json
from pathlib import Path
from typing import Dict, List
from detection.zones import Zone


class ZoneConfigManager:
    """Manages zone configurations per camera."""
    
    CONFIG_DIR = Path("zone_configs")
    
    def __init__(self):
        self.CONFIG_DIR.mkdir(exist_ok=True)
    
    def _get_path(self, camera_id: str) -> Path:
        return self.CONFIG_DIR / f"{camera_id}.json"
    
    def load_zones(self, camera_id: str) -> List[Zone]:
        """Load zones for a specific camera."""
        path = self._get_path(camera_id)
        if not path.exists():
            return []
        
        with open(path) as f:
            data = json.load(f)
        
        return [
            Zone(
                name=z["name"],
                points=[tuple(p) for p in z["points"]],
                color=tuple(z.get("color", [0, 0, 255])),
                severity=z.get("severity", "high")
            )
            for z in data.get("zones", [])
        ]
    
    def save_zones(self, camera_id: str, zones_data: List[dict]):
        """Save zones for a specific camera."""
        path = self._get_path(camera_id)
        with open(path, "w") as f:
            json.dump({"zones": zones_data}, f, indent=2)
        print(f"[ZoneConfig] Saved {len(zones_data)} zones for {camera_id}")
    
    def delete_zones(self, camera_id: str):
        """Delete zone config for a camera."""
        path = self._get_path(camera_id)
        if path.exists():
            path.unlink()