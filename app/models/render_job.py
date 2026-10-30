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
        default=lambda: str(uuid.uuid4()),
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
    quality_preset = Column(String(32), default="high")
    modes = Column(String(256), nullable=True)
    overwrite = Column(Boolean, default=True)
    normalize_audio = Column(Boolean, default=True)
    target_lufs = Column(Float, default=-14.0)

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

    # Upload staging / selection
    is_selected_for_upload = Column(Boolean, default=False, index=True)
    selected_format = Column(String(64), nullable=True)
    upload_metadata = Column(Text, nullable=True)

    # Phase 8: autonomous staging & native YouTube scheduling
    auto_staged = Column(Boolean, default=False, index=True)
    highlight_candidate_id = Column(String(64), nullable=True, index=True)
    scheduled_publish_at = Column(DateTime, nullable=True, index=True)

    # YouTube upload tracking
    youtube_video_id = Column(String(64), nullable=True)
    youtube_upload_status = Column(String(32), default="not_uploaded", index=True)
    youtube_upload_progress = Column(Float, default=0.0)
    youtube_upload_url = Column(String(256), nullable=True)
    youtube_uploaded_at = Column(DateTime, nullable=True)
    youtube_upload_error = Column(Text, nullable=True)

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
            "quality_preset": self.quality_preset or "high",
            "normalize_audio": bool(self.normalize_audio)
            if self.normalize_audio is not None
            else True,
            "target_lufs": self.target_lufs if self.target_lufs is not None else -14.0,
            "modes": [m.strip() for m in self.modes.split(",") if m.strip()]
            if self.modes
            else [],
            "output_dir": self.output_dir,
            "landscape_path": self.landscape_path,
            "vertical_blur_path": self.vertical_blur_path,
            "vertical_crop_path": self.vertical_crop_path,
            "manifest_path": self.manifest_path,
            "encoder_used": self.encoder_used,
            "render_duration_seconds": self.render_duration_seconds,
            "error_message": self.error_message,
            "celery_task_id": self.celery_task_id,
            "is_selected_for_upload": bool(self.is_selected_for_upload),
            "selected_format": self.selected_format,
            "upload_metadata": self.upload_metadata,
            "auto_staged": bool(self.auto_staged),
            "highlight_candidate_id": self.highlight_candidate_id,
            "scheduled_publish_at": self.scheduled_publish_at.isoformat()
            if self.scheduled_publish_at
            else None,
            "youtube_video_id": self.youtube_video_id,
            "youtube_upload_status": self.youtube_upload_status or "not_uploaded",
            "youtube_upload_progress": self.youtube_upload_progress or 0.0,
            "youtube_upload_url": self.youtube_upload_url,
            "youtube_uploaded_at": self.youtube_uploaded_at.isoformat()
            if self.youtube_uploaded_at
            else None,
            "youtube_upload_error": self.youtube_upload_error,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "completed_at": self.completed_at.isoformat()
            if self.completed_at
            else None,
        }
