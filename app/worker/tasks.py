"""Celery tasks for background processing (downloads, video rendering).

Deprecated: Tasks have been broken down and moved to their respective service modules
(app.services.videos and app.services.renders) to eliminate circular import issues.
This module re-exports them for backwards compatibility.
"""

from app.database import get_task_db_session
from app.services.renders import (
    bulk_delete_renders_celery_task,
    execute_bulk_delete_job,
    execute_render_job,
    render_clip_celery_task,
)
from app.services.videos import download_video_celery_task, execute_download_job
from app.services.youtube_uploader import (
    batch_upload_clips_celery_task,
    upload_clip_celery_task,
)

__all__ = [
    "batch_upload_clips_celery_task",
    "bulk_delete_renders_celery_task",
    "download_video_celery_task",
    "execute_bulk_delete_job",
    "execute_download_job",
    "execute_render_job",
    "get_task_db_session",
    "render_clip_celery_task",
    "upload_clip_celery_task",
]
