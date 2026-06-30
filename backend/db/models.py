"""
models.py — Database models for intrusion events
"""

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text
from sqlalchemy.sql import func
from .database import Base


class IntrusionEvent(Base):
    __tablename__ = "intrusion_events"
    
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    zone_name = Column(String(100), nullable=False)
    confidence = Column(Float, nullable=False)
    severity = Column(String(20), default="high")
    snapshot_path = Column(Text, nullable=True)
    resolved = Column(Boolean, default=False)
    bbox_x1 = Column(Integer, nullable=True)
    bbox_y1 = Column(Integer, nullable=True)
    bbox_x2 = Column(Integer, nullable=True)
    bbox_y2 = Column(Integer, nullable=True)
    
    def to_dict(self):
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "zone_name": self.zone_name,
            "confidence": self.confidence,
            "severity": self.severity,
            "snapshot_path": self.snapshot_path,
            "resolved": self.resolved,
            "bbox": [self.bbox_x1, self.bbox_y1, self.bbox_x2, self.bbox_y2]
        }