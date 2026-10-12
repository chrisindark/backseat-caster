"""Celery tasks for background processing (downloads, video rendering)."""

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config import settings
from app.database import SessionLocal
from app.models.render_job import RenderJob
from app.models.video import Video
from app.rendering.config import RenderConfig
from app.rendering.engine import RenderEngine
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
        logger.exception("Failed downloading video %s", video_id)
        try:
            if video:
                video.download_status = "failed"
                video.error_message = str(e)
                db.commit()
        except Exception as e2:
            logger.error("Error committing download job failure: %s", e2)
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


def get_task_db_session():
    try:
        import sys

        main_mod = sys.modules.get("app.main")
        if main_mod and hasattr(main_mod, "app"):
            fastapi_app = main_mod.app
            from app.database import get_db

            if (
                hasattr(fastapi_app, "dependency_overrides")
                and get_db in fastapi_app.dependency_overrides
            ):
                gen = fastapi_app.dependency_overrides[get_db]()
                return next(gen)
    except Exception:
        pass
    return SessionLocal()


def execute_render_job(
    job_id: str,
    celery_task_instance=None,
    db_session=None,
) -> dict[str, Any]:
    """Core clip rendering execution logic shared by Celery and background workers."""
    is_external_session = db_session is not None
    db = db_session if db_session is not None else get_task_db_session()
    job = None
    try:
        job = db.query(RenderJob).filter(RenderJob.id == job_id).first()
        if not job:
            logger.error("Render job %s not found in database", job_id)
            return {"status": "failed", "error": f"Render job {job_id} not found"}

        job.status = "rendering"
        job.progress = 5.0
        job.error_message = None
        db.commit()

        if celery_task_instance:
            celery_task_instance.update_state(
                state="PROGRESS",
                meta={"progress": 5.0, "stage": "Starting rendering job"},
            )

        # 1. Resolve source video file
        video = db.query(Video).filter(Video.id == job.video_id).first()
        source_file = None
        if video and video.local_file_path and Path(video.local_file_path).exists():
            source_file = Path(video.local_file_path)
        else:
            matches = list(settings.downloads_path.glob(f"{job.video_id}.*"))
            if matches:
                source_file = matches[0]

        if not source_file or not source_file.exists():
            raise FileNotFoundError(
                f"Local video file not found for video ID '{job.video_id}'. Download the VOD first."
            )

        out_dir = settings.renders_path / job.clip_id
        narr_file = Path(job.narration_path).resolve() if job.narration_path else None

        config = RenderConfig(
            preferred_encoder=job.encoder,
            crop_preset=job.crop_preset
            if job.crop_preset in ("third_person", "cinematic", "direct_crop", "custom")
            else "third_person",
            crop_blur_padding=job.crop_blur_padding
            if job.crop_blur_padding is not None
            else 0.3333,
            api_prefix=settings.API_PREFIX,
        )
        engine = RenderEngine(config=config)

        def on_progress(pct: float, stage: str):
            try:
                job.progress = pct
                db.commit()
                if celery_task_instance:
                    celery_task_instance.update_state(
                        state="PROGRESS",
                        meta={"progress": pct, "stage": stage},
                    )
            except Exception as prog_err:
                logger.warning("Error recording render job progress: %s", prog_err)

        result = engine.render_clip(
            source_path=source_file,
            start_seconds=job.start_seconds,
            duration_seconds=job.duration_seconds,
            output_dir=out_dir,
            clip_id=job.clip_id,
            narration_path=narr_file,
            overwrite=job.overwrite,
            crop_preset=job.crop_preset,
            crop_blur_padding=job.crop_blur_padding,
            progress_callback=on_progress,
        )

        prefix = settings.API_PREFIX
        job.status = "completed"
        job.progress = 100.0
        job.output_dir = str(out_dir)
        job.landscape_path = f"{prefix}/renders/{job.clip_id}/stream/landscape"
        job.vertical_blur_path = f"{prefix}/renders/{job.clip_id}/stream/vertical_blur"
        job.vertical_crop_path = f"{prefix}/renders/{job.clip_id}/stream/vertical_crop"
        job.manifest_path = f"{prefix}/renders/{job.clip_id}/stream/manifest"
        job.encoder_used = result.encoder_used
        job.render_duration_seconds = result.render_duration_seconds
        job.completed_at = datetime.now(UTC)
        job.error_message = None
        db.commit()

        logger.info(
            "Successfully completed render job %s (clip_id: %s) in %.2fs",
            job_id,
            job.clip_id,
            result.render_duration_seconds,
        )
        return {
            "status": "completed",
            "job_id": job_id,
            "clip_id": job.clip_id,
            "output_dir": str(out_dir),
            "render_duration_seconds": result.render_duration_seconds,
        }

    except Exception as e:
        logger.exception("Failed rendering job %s: %s", job_id, e)
        try:
            if job:
                job.status = "failed"
                job.error_message = str(e)
                db.commit()
        except Exception:
            pass
        return {"status": "failed", "job_id": job_id, "error": str(e)}
    finally:
        import sys

        main_mod = sys.modules.get("app.main")
        fastapi_app = getattr(main_mod, "app", None) if main_mod else None
        from app.database import get_db

        is_overridden = bool(
            fastapi_app
            and hasattr(fastapi_app, "dependency_overrides")
            and get_db in fastapi_app.dependency_overrides
        )
        if not is_external_session and not is_overridden:
            db.close()


@celery_app.task(bind=True, name="render_clip_task")
def render_clip_celery_task(self, job_id: str):
    """Celery task for video clip rendering."""
    logger.info(
        "Celery task started: rendering job %s (task_id: %s)",
        job_id,
        self.request.id,
    )
    return execute_render_job(job_id=job_id, celery_task_instance=self)
