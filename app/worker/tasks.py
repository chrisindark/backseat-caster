"""Celery tasks for background processing (downloads, future video rendering)."""

import logging
from typing import Any

from app.database import SessionLocal
from app.services import VideoService
from app.services.youtube import YouTubeService
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


def execute_download_job(
    video_id: str,
    quality: str = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
    celery_task_instance=None,
) -> dict[str, Any]:
    """Core download execution logic shared by Celery and background workers."""
    db = SessionLocal()
    last_reported_progress = 0.0

    try:
        video = VideoService.get_video_by_id(db=db, video_id=video_id)
        if not video:
            logger.error("Video ID %s not found in database", video_id)
            return {"status": "failed", "error": f"Video {video_id} not found"}

        video.download_status = "downloading"
        video.download_progress = 1.0
        video.error_message = None
        db.commit()

        def on_progress(data: dict[str, Any]):
            nonlocal last_reported_progress
            pct = data.get("progress", 0.0)
            if pct - last_reported_progress >= 5.0 or pct >= 99.0:
                last_reported_progress = pct
                try:
                    video.download_progress = pct
                    db.commit()
                    if celery_task_instance:
                        celery_task_instance.update_state(
                            state="PROGRESS",
                            meta={"progress": pct, "speed": data.get("speed")},
                        )
                except Exception as commit_err:
                    logger.warning("Error committing progress update: %s", commit_err)

        result = YouTubeService.download_video(
            video_id=video_id, quality=quality, progress_callback=on_progress
        )

        video.download_status = "completed"
        video.download_progress = 100.0
        video.is_downloaded = True
        video.local_file_path = result["local_file_path"]
        video.file_size_bytes = result["file_size_bytes"]
        video.error_message = None
        db.commit()

        logger.info(
            "Successfully downloaded video %s to %s",
            video_id,
            result["local_file_path"],
        )
        return {
            "status": "completed",
            "video_id": video_id,
            "file_path": result["local_file_path"],
            "file_size": result["file_size_bytes"],
        }

    except Exception as e:
        logger.exception("Failed downloading video %s: %s", video_id, e)
        try:
            if video:
                video.download_status = "failed"
                video.error_message = str(e)
                db.commit()
        except Exception:
            pass
        return {"status": "failed", "video_id": video_id, "error": str(e)}
    finally:
        db.close()


@celery_app.task(bind=True, name="download_video_task")
def download_video_celery_task(
    self,
    video_id: str,
    quality: str = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
):
    """Celery task for video download."""
    logger.info(
        "Celery task started: downloading video %s (task_id: %s)",
        video_id,
        self.request.id,
    )
    return execute_download_job(
        video_id=video_id, quality=quality, celery_task_instance=self
    )
