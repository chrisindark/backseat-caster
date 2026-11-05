"""VideoAnalyticsSnapshot model for tracking YouTube view velocity and performance over time."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text

from app.database import Base


def utc_now():
    return datetime.now(UTC)


class VideoAnalyticsSnapshot(Base):
    """Historical checkpoint snapshot of a published YouTube Short's metrics."""

    __tablename__ = "video_analytics_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(
        String(64),
        ForeignKey("render_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    clip_id = Column(String(128), nullable=False, index=True)
    youtube_video_id = Column(String(64), nullable=False, index=True)

    recorded_at = Column(DateTime, default=utc_now, nullable=False, index=True)
    published_at = Column(DateTime, nullable=True)
    hours_since_publish = Column(Float, nullable=False, default=0.0, index=True)

    view_count = Column(Integer, default=0, nullable=False)
    like_count = Column(Integer, default=0, nullable=False)
    comment_count = Column(Integer, default=0, nullable=False)

    raw_payload = Column(Text, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "job_id": self.job_id,
            "clip_id": self.clip_id,
            "youtube_video_id": self.youtube_video_id,
            "recorded_at": self.recorded_at.isoformat() if self.recorded_at else None,
            "published_at": self.published_at.isoformat()
            if self.published_at
            else None,
            "hours_since_publish": round(self.hours_since_publish, 2),
            "view_count": self.view_count,
            "like_count": self.like_count,
            "comment_count": self.comment_count,
        }
