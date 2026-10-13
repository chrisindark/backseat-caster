"""HighlightCandidate SQLAlchemy model."""

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Column, DateTime, Float, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


def utc_now():
    return datetime.now(UTC)


class HighlightCandidate(Base):
    """Represents a mined gameplay highlight candidate clip."""

    __tablename__ = "highlight_candidates"

    id = Column(String(64), primary_key=True, index=True)  # e.g. cand_mvr_91a2b
    video_id = Column(
        String(64),
        index=True,
        nullable=False,
    )
    start_seconds = Column(Float, nullable=False)
    end_seconds = Column(Float, nullable=False)
    duration_seconds = Column(Float, nullable=False)
    score = Column(Float, index=True, nullable=False)  # Quality score 0.0 - 1.0
    event_type = Column(
        String(64), index=True, nullable=False
    )  # team_wipe, triple_ko, double_ko, etc.
    game = Column(String(64), default="")
    details_json = Column(Text, nullable=False)  # Serialized HighlightDetails
    thumbnail_url = Column(String(1024), nullable=True)
    thumbnail_path = Column(String(1024), nullable=True)
    peak_timestamp = Column(Float, default=0.0)
    suggested_title = Column(String(512), nullable=True)
    suggested_tags_json = Column(Text, nullable=True)  # JSON array of strings

    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    video = relationship(
        "Video",
        primaryjoin="HighlightCandidate.video_id == Video.id",
        foreign_keys="HighlightCandidate.video_id",
        back_populates="highlight_candidates",
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict matching candidate JSON schema contract."""
        details_dict: dict[str, Any] = {}
        if self.details_json:
            try:
                details_dict = json.loads(self.details_json)
            except Exception:
                details_dict = {}

        tags_list: list[str] = []
        if self.suggested_tags_json:
            try:
                tags_list = json.loads(self.suggested_tags_json)
            except Exception:
                tags_list = []

        return {
            "candidate_id": self.id,
            "video_id": self.video_id,
            "start_seconds": self.start_seconds,
            "end_seconds": self.end_seconds,
            "duration_seconds": self.duration_seconds,
            "score": self.score,
            "event_type": self.event_type,
            "game": self.game or "generic",
            "details": details_dict,
            "thumbnail_url": self.thumbnail_url,
            "thumbnail_path": self.thumbnail_path,
            "peak_timestamp": self.peak_timestamp,
            "suggested_title": self.suggested_title or "",
            "suggested_tags": tags_list,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
