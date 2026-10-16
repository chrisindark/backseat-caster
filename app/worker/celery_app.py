"""Celery application instance and configuration."""

from celery import Celery

from app.config import settings

celery_app = Celery(
    "backseatcaster_worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.services.videos",
        "app.services.renders",
        "app.services.youtube_uploader",
        "app.services.highlight.service",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=1800,
    broker_connection_retry=True,
    broker_connection_retry_on_startup=True,
    broker_connection_max_retries=3,
    worker_pool="solo",
)

# Avoid spawn/forkserver-specific fast trace failures on Python 3.14.
celery_app.use_fast_trace_task = False


@celery_app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    pass


from celery.signals import worker_process_init  # noqa: E402


@worker_process_init.connect
def on_worker_process_init(**kwargs):
    """Ensure child Celery worker processes initialize an isolated database connection pool."""
    from app.database import engine

    engine.dispose(close=False)
