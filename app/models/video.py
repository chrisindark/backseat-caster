"""Video SQLAlchemy model."""

from datetime import UTC, datetime

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


def utc_now():
    return datetime.now(UTC)


class Video(Base):
    """Represents a YouTube video item and its local download/rendering status."""

    __tablename__ = "videos"

    id = Column(String(64), primary_key=True, index=True)  # YouTube Video ID
    title = Column(String(512), nullable=False, index=True)
    description = Column(Text, nullable=True)
    thumbnail_url = Column(String(1024), nullable=True)
    duration = Column(Integer, default=0)  # duration in seconds
    duration_formatted = Column(String(32), default="0:00")
    channel_name = Column(String(256), nullable=True, index=True)
    channel_id = Column(String(128), nullable=True)
    channel_url = Column(String(512), nullable=True)
    view_count = Column(Integer, default=0)
    published_at = Column(String(64), nullable=True)
    webpage_url = Column(String(1024), nullable=False)

    # Local download state
    is_downloaded = Column(Boolean, default=False, index=True)
    local_file_path = Column(String(1024), nullable=True)
    file_size_bytes = Column(Integer, nullable=True)
    download_status = Column(
        String(32), default="not_downloaded", index=True
    )  # not_downloaded, pending, downloading, completed, failed
    download_progress = Column(Float, default=0.0)
    error_message = Column(Text, nullable=True)

    # Highlight candidate mining state
    highlight_status = Column(
        String(32), default="idle", index=True
    )  # idle, pending, scanning, completed, failed
    highlight_progress = Column(Float, default=0.0)
    highlight_stage = Column(String(128), default="")
    highlight_error = Column(Text, nullable=True)
    highlight_task_id = Column(String(128), nullable=True)

    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    highlight_candidates = relationship(
        "HighlightCandidate",
        primaryjoin="Video.id == HighlightCandidate.video_id",
        foreign_keys="HighlightCandidate.video_id",
        back_populates="video",
        cascade="all, delete-orphan",
        order_by="desc(HighlightCandidate.score)",
    )
    highlight_runs = relationship(
        "HighlightRun",
        primaryjoin="Video.id == HighlightRun.video_id",
        foreign_keys="HighlightRun.video_id",
        back_populates="video",
        cascade="all, delete-orphan",
        order_by="desc(HighlightRun.created_at)",
    )

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "thumbnail_url": self.thumbnail_url,
            "duration": self.duration,
            "duration_formatted": self.duration_formatted,
            "channel_name": self.channel_name,
            "channel_id": self.channel_id,
            "channel_url": self.channel_url,
            "view_count": self.view_count,
            "published_at": self.published_at,
            "webpage_url": self.webpage_url,
            "is_downloaded": self.is_downloaded,
            "local_file_path": self.local_file_path,
            "file_size_bytes": self.file_size_bytes,
            "download_status": self.download_status,
            "download_progress": self.download_progress,
            "error_message": self.error_message,
            "highlight_status": self.highlight_status or "idle",
            "highlight_progress": self.highlight_progress or 0.0,
            "highlight_stage": self.highlight_stage or "",
            "highlight_error": self.highlight_error,
            "highlight_task_id": self.highlight_task_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
