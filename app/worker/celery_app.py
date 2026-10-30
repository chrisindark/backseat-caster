"""Celery application instance and configuration."""

from datetime import timedelta

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
        "app.services.auto_pipeline",
        "app.services.watch_folder",
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
    """Register the optional maintenance sweep and watch folder poll for Celery beat."""
    interval = settings.AUTO_PIPELINE_INTERVAL_MINUTES
    if interval > 0:
        sender.add_periodic_task(
            timedelta(minutes=interval),
            sender.signature(
                "auto_pipeline_task",
                kwargs={
                    "stage": True,
                    "cleanup": settings.AUTO_CLEANUP_UPLOADED_RENDERS,
                    "clean_vod": settings.AUTO_CLEANUP_VOD,
                },
            ),
            name="auto-pipeline-maintenance",
        )

    # Tier 2: zero-click OBS ingest. Only scheduled when a folder is configured,
    # so a plain install never spawns a pointless periodic task.
    watch_interval = settings.WATCH_POLL_INTERVAL_MINUTES
    if settings.watch_path is not None and watch_interval > 0:
        sender.add_periodic_task(
            timedelta(minutes=watch_interval),
            sender.signature("watch_folder_scan_task"),
            name="watch-folder-scan",
        )


from celery.signals import worker_process_init  # noqa: E402


@worker_process_init.connect
def on_worker_process_init(**kwargs):
    """Ensure child Celery worker processes initialize an isolated database connection pool."""
    from app.database import engine

    engine.dispose(close=False)
