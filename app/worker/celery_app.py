"""Celery application instance and configuration."""

from celery import Celery

from app.config import settings

celery_app = Celery(
    "backseatcaster_worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.worker.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=1800,
    broker_connection_retry=False,
    broker_connection_retry_on_startup=False,
    broker_connection_max_retries=0,
)
