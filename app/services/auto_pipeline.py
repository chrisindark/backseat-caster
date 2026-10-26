"""Autonomous maintenance pipeline for rendered clips.

Two jobs run together:

1. Cleanup: delete local render folders whose clips have already been uploaded
   to YouTube. ``RenderJob`` rows are preserved so upload history, scheduling
   metadata and the video catalog stay intact; only disk usage is reclaimed.
2. Sweep staging: walk every downloaded video that still has unstaged
   highlights and stage its next ``AUTO_STAGE_TOP_N`` candidates, so the
   backlog of top-rated highlights is consumed in batches instead of only
   immediately after highlight detection.

The pipeline can be triggered on demand via ``POST /api/v1/renders/auto-pipeline``
or scheduled through Celery beat by setting ``AUTO_PIPELINE_INTERVAL_MINUTES``.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_task_db_session
from app.models.render_job import RenderJob
from app.models.video import Video
from app.services.auto_stage import AutoStageService
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)

ACTIVE_RENDER_STATUSES = ("pending", "rendering", "queued")


def _format_bytes(size: int) -> str:
    """Render a byte count as a compact human-readable string."""
    mb = size / (1024 * 1024)
    if mb >= 1024:
        return f"{(mb / 1024):.2f} GB"
    return f"{mb:.1f} MB"


class AutoPipelineService:
    """Reclaim uploaded render storage and batch-stage the best highlights."""

    @staticmethod
    def _is_uploaded(job: RenderJob) -> bool:
        return (
            job.youtube_upload_status == "completed"
            or job.youtube_upload_url is not None
        )

    @classmethod
    def cleanup_uploaded_renders(
        cls,
        db: Session,
        *,
        clean_vod: bool | None = None,
    ) -> dict[str, Any]:
        """Delete render folders for clips already uploaded to YouTube.

        Database records are never removed: the render disappears from the disk
        listing but its upload metadata and YouTube link remain queryable.
        """
        if clean_vod is None:
            clean_vod = settings.AUTO_CLEANUP_VOD

        renders_root = settings.renders_path
        jobs = (
            db.query(RenderJob)
            .filter(
                or_(
                    RenderJob.youtube_upload_status == "completed",
                    RenderJob.youtube_upload_url.isnot(None),
                )
            )
            .all()
        )

        reclaimed_bytes = 0
        cleaned_clip_ids: list[str] = []
        uploaded_video_ids: set[str] = set()

        for job in jobs:
            uploaded_video_ids.add(job.video_id)
            candidate_dirs: list[Path] = []
            if job.clip_id:
                candidate_dirs.append(renders_root / job.clip_id)
            if job.output_dir:
                output_dir = Path(job.output_dir)
                if output_dir not in candidate_dirs:
                    candidate_dirs.append(output_dir)

            for clip_dir in candidate_dirs:
                if not clip_dir.exists() or not clip_dir.is_dir():
                    continue
                try:
                    dir_size = sum(
                        f.stat().st_size for f in clip_dir.rglob("*") if f.is_file()
                    )
                    shutil.rmtree(clip_dir)
                    reclaimed_bytes += dir_size
                    if job.clip_id not in cleaned_clip_ids:
                        cleaned_clip_ids.append(job.clip_id)
                except OSError as exc:
                    logger.warning(
                        "Could not remove render folder %s for %s: %s",
                        clip_dir,
                        job.clip_id,
                        exc,
                    )

        vod_deleted_count = 0
        if clean_vod:
            for video_id in uploaded_video_ids:
                if not cls._can_clean_vod(db, video_id):
                    continue
                reclaimed_bytes += cls._remove_vod_files(db, video_id)
                vod_deleted_count += 1

        messages: list[str] = []
        if cleaned_clip_ids:
            messages.append(
                f"Cleaned {len(cleaned_clip_ids)} uploaded render(s), "
                f"reclaimed {_format_bytes(reclaimed_bytes)}"
            )
        if vod_deleted_count:
            messages.append(f"removed {vod_deleted_count} source VOD(s)")
        message = (
            ", ".join(messages) + "."
            if messages
            else "No uploaded render folders needed cleanup."
        )
        logger.info("Auto-cleanup: %s", message)

        return {
            "clips_cleaned": len(cleaned_clip_ids),
            "clip_ids": cleaned_clip_ids,
            "videos_processed": len(uploaded_video_ids),
            "bytes_reclaimed": reclaimed_bytes,
            "reclaimed_formatted": _format_bytes(reclaimed_bytes),
            "vod_deleted_count": vod_deleted_count,
            "message": message,
        }

    @classmethod
    def _can_clean_vod(cls, db: Session, video_id: str) -> bool:
        """A VOD is safe to delete only when every completed render is uploaded."""
        jobs = db.query(RenderJob).filter(RenderJob.video_id == video_id).all()
        if not jobs:
            return False
        if any(job.status in ACTIVE_RENDER_STATUSES for job in jobs):
            return False
        completed = [job for job in jobs if job.status == "completed"]
        if not completed:
            return False
        return all(cls._is_uploaded(job) for job in completed)

    @classmethod
    def _remove_vod_files(cls, db: Session, video_id: str) -> int:
        """Delete the source VOD and thumbnail, resetting download state."""
        video = db.query(Video).filter(Video.id == video_id).first()
        if not video:
            return 0

        removed_bytes = 0
        paths: list[Path] = []
        if video.local_file_path:
            paths.append(Path(video.local_file_path))
        paths.append(settings.downloads_path / f"{video_id}.mp4")
        paths.append(settings.downloads_path / f"{video_id}_thumb.jpg")

        for path in dict.fromkeys(paths):
            if not path.exists() or not path.is_file():
                continue
            try:
                removed_bytes += path.stat().st_size
                path.unlink()
            except OSError as exc:
                logger.warning("Could not remove %s for %s: %s", path, video_id, exc)

        video.is_downloaded = False
        video.download_status = "not_downloaded"
        video.download_progress = 0.0
        video.local_file_path = None
        video.file_size_bytes = None
        db.commit()
        return removed_bytes

    @classmethod
    def run(
        cls,
        db: Session,
        *,
        stage: bool = True,
        cleanup: bool = True,
        clean_vod: bool | None = None,
        top_n: int | None = None,
        min_score: float | None = None,
        clipping_mode: str | None = None,
        schedule: bool = True,
        background_tasks: Any = None,
    ) -> dict[str, Any]:
        """Stage the next top candidates, then reclaim uploaded render files.

        Staging runs first because it needs the source VODs that cleanup may
        remove later in the same pass.
        """
        staging: dict[str, Any] = {
            "videos_processed": 0,
            "staged_count": 0,
            "clips": [],
            "message": "Staging skipped.",
        }
        if stage:
            staging = AutoStageService.stage_all_top_candidates(
                db,
                top_n=top_n,
                min_score=min_score,
                clipping_mode=clipping_mode,
                schedule=schedule,
                background_tasks=background_tasks,
            )

        cleanup_result: dict[str, Any] = {
            "clips_cleaned": 0,
            "clip_ids": [],
            "videos_processed": 0,
            "bytes_reclaimed": 0,
            "reclaimed_formatted": _format_bytes(0),
            "vod_deleted_count": 0,
            "message": "Cleanup skipped.",
        }
        if cleanup:
            cleanup_result = cls.cleanup_uploaded_renders(db, clean_vod=clean_vod)

        parts = [staging["message"], cleanup_result["message"]]
        return {
            "staged_count": staging["staged_count"],
            "videos_processed": staging["videos_processed"],
            "clips_cleaned": cleanup_result["clips_cleaned"],
            "bytes_reclaimed": cleanup_result["bytes_reclaimed"],
            "reclaimed_formatted": cleanup_result["reclaimed_formatted"],
            "vod_deleted_count": cleanup_result["vod_deleted_count"],
            "message": " ".join(part for part in parts if part),
        }


def execute_auto_pipeline_job(
    db_session: Session | None = None,
    *,
    stage: bool = True,
    cleanup: bool = True,
    clean_vod: bool | None = None,
    top_n: int | None = None,
    min_score: float | None = None,
    clipping_mode: str | None = None,
    schedule: bool = True,
) -> dict[str, Any]:
    """Run the maintenance pipeline with an owned or caller-provided session."""
    db = db_session if db_session is not None else get_task_db_session()
    try:
        return AutoPipelineService.run(
            db,
            stage=stage,
            cleanup=cleanup,
            clean_vod=clean_vod,
            top_n=top_n,
            min_score=min_score,
            clipping_mode=clipping_mode,
            schedule=schedule,
        )
    except Exception:
        logger.exception("Auto-pipeline run failed")
        db.rollback()
        raise
    finally:
        if db_session is None:
            db.close()


@celery_app.task(bind=True, name="auto_pipeline_task")
def auto_pipeline_celery_task(
    self,
    stage: bool = True,
    cleanup: bool = True,
    clean_vod: bool | None = None,
    top_n: int | None = None,
    min_score: float | None = None,
    clipping_mode: str | None = None,
    schedule: bool = True,
):
    """Celery entry point for the cleanup + batch staging pipeline."""
    logger.info("Celery auto-pipeline started (task_id: %s)", self.request.id)
    return execute_auto_pipeline_job(
        stage=stage,
        cleanup=cleanup,
        clean_vod=clean_vod,
        top_n=top_n,
        min_score=min_score,
        clipping_mode=clipping_mode,
        schedule=schedule,
    )
