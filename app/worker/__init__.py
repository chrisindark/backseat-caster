"""Worker package."""

from app.worker.celery_app import celery_app
from app.worker.helpers import is_celery_broker_online

__all__ = [
    "celery_app",
    "download_video_celery_task",
    "execute_download_job",
    "execute_render_job",
    "is_celery_broker_online",
    "render_clip_celery_task",
]


def __getattr__(name: str):
    if name in ("download_video_celery_task", "execute_download_job"):
        from app.services import videos

        return getattr(videos, name)
    if name in ("render_clip_celery_task", "execute_render_job"):
        from app.services import renders

        return getattr(renders, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
