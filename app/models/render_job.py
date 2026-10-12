"""RenderJob SQLAlchemy model."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, Column, DateTime, Float, String, Text

from app.database import Base


def utc_now():
    return datetime.now(UTC)


class RenderJob(Base):
    """Represents a background clip render job and its progress/outputs."""

    __tablename__ = "render_jobs"

    id = Column(
        String(64),
        primary_key=True,
        index=True,
        default=uuid.uuid4(),
    )
    clip_id = Column(String(128), index=True, nullable=False)
    video_id = Column(String(64), index=True, nullable=False)

    # Job lifecycle: pending -> rendering -> completed / failed
    status = Column(String(32), default="pending", index=True)
    progress = Column(Float, default=0.0)

    # Render inputs
    start_seconds = Column(Float, nullable=False)
    duration_seconds = Column(Float, nullable=False)
    narration_path = Column(String(1024), nullable=True)
    encoder = Column(String(64), default="auto")
    # Crop preset values: third_person, direct_center, cinematic_balanced
    crop_preset = Column(String(64), default="third_person")
    crop_blur_padding = Column(Float, default=0.3333)
    overwrite = Column(Boolean, default=True)

    # Outputs
    output_dir = Column(String(1024), nullable=True)
    landscape_path = Column(String(1024), nullable=True)
    vertical_blur_path = Column(String(1024), nullable=True)
    vertical_crop_path = Column(String(1024), nullable=True)
    manifest_path = Column(String(1024), nullable=True)
    encoder_used = Column(String(64), nullable=True)
    render_duration_seconds = Column(Float, nullable=True)

    # Task & error tracking
    celery_task_id = Column(String(128), nullable=True)
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)
    completed_at = Column(DateTime, nullable=True)

    def to_dict(self):
        return {
            "job_id": self.id,
            "clip_id": self.clip_id,
            "video_id": self.video_id,
            "status": self.status,
            "progress": self.progress,
            "start_seconds": self.start_seconds,
            "duration_seconds": self.duration_seconds,
            "narration_path": self.narration_path,
            "encoder": self.encoder,
            "crop_preset": self.crop_preset,
            "crop_blur_padding": self.crop_blur_padding,
            "output_dir": self.output_dir,
            "landscape_path": self.landscape_path,
            "vertical_blur_path": self.vertical_blur_path,
            "vertical_crop_path": self.vertical_crop_path,
            "manifest_path": self.manifest_path,
            "encoder_used": self.encoder_used,
            "render_duration_seconds": self.render_duration_seconds,
            "error_message": self.error_message,
            "celery_task_id": self.celery_task_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "completed_at": self.completed_at.isoformat()
            if self.completed_at
            else None,
        }
