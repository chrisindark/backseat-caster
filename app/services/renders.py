"""Render service containing database, Celery dispatch, and business logic for video renders."""

import json
import logging
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_task_db_session
from app.models.render_job import RenderJob
from app.models.video import Video
from app.rendering.config import RenderConfig
from app.rendering.engine import RenderEngine
from app.schemas.render import (
    RenderClipRequest,
    RenderClipResponse,
    RenderJobResponse,
    RenderJobUpdateRequest,
    UploadSelectionRequest,
)
from app.services.upload_metadata import (
    build_description,
    build_tags,
)
from app.worker import helpers
from app.worker.celery_app import celery_app


def is_celery_broker_online() -> bool:
    """Check whether Celery broker is online, delegating dynamically to helpers."""
    return helpers.is_celery_broker_online()


logger = logging.getLogger(__name__)


class RenderService:
    """Service handling render jobs, manifest resolution, database sync, and background task dispatch."""

    @staticmethod
    def format_render_manifest(
        manifest: dict[str, Any], clip_id: str | None = None
    ) -> dict[str, Any]:
        """Ensure manifest contains streamable paths for media and manifest endpoints."""
        cid = clip_id or manifest.get("clip_id") or ""
        prefix = settings.API_PREFIX
        manifest_stream = f"{prefix}/renders/{cid}/stream/manifest"
        manifest["manifest_path"] = manifest_stream

        outputs = manifest.get("outputs", {})
        if isinstance(outputs, dict):
            for mode_key, mode_meta in outputs.items():
                if isinstance(mode_meta, dict):
                    mode_meta["path"] = f"{prefix}/renders/{cid}/stream/{mode_key}"
            manifest["outputs"] = outputs

        # Legacy top-level paths for backwards compatibility
        if "landscape" in outputs or "landscape_path" not in manifest:
            manifest["landscape_path"] = f"{prefix}/renders/{cid}/stream/landscape"

        if "vertical_blur" in outputs or "vertical_blur_path" not in manifest:
            manifest["vertical_blur_path"] = (
                f"{prefix}/renders/{cid}/stream/vertical_blur"
            )

        crop_candidates = [
            m
            for m in (
                "vertical_crop",
                "third_person",
                "direct_crop",
                "cinematic",
                "custom",
            )
            if m in outputs
        ]
        if crop_candidates:
            primary_crop = crop_candidates[0]
            manifest["vertical_crop_path"] = (
                f"{prefix}/renders/{cid}/stream/{primary_crop}"
            )
        elif "vertical_crop_path" not in manifest:
            manifest["vertical_crop_path"] = (
                f"{prefix}/renders/{cid}/stream/vertical_crop"
            )

        if "source" not in manifest and "source_file" in manifest:
            source_meta = manifest.get("source_metadata", {})
            manifest["source"] = {
                "path": manifest.get("source_file"),
                **source_meta,
            }

        return manifest

    @staticmethod
    def resolve_source_video_file(db: Session, video_id: str) -> Path | None:
        """Resolve source video file from database record or directly from downloads directory."""
        video = db.query(Video).filter(Video.id == video_id).first()
        if video and video.local_file_path and Path(video.local_file_path).exists():
            return Path(video.local_file_path)

        matches = list(settings.downloads_path.glob(f"{video_id}.*"))
        if matches and matches[0].exists():
            return matches[0]

        return None

    @staticmethod
    def create_render(
        db: Session,
        request: RenderClipRequest,
        background_tasks: BackgroundTasks | None = None,
    ) -> RenderClipResponse:
        """
        Validate source video, persist RenderJob in database, and dispatch execution
        either synchronously, via Celery worker, or via FastAPI BackgroundTasks.
        """
        source_file = RenderService.resolve_source_video_file(
            db=db, video_id=request.video_id
        )
        if not source_file or not source_file.exists():
            raise FileNotFoundError(
                f"Local video file not found for ID: {request.video_id}. Download the VOD first."
            )

        clip_id = (
            request.clip_id
            or f"clip_{request.video_id}_{int(request.start_seconds)}s_{int(request.duration_seconds)}s"
        )
        renders_root = settings.renders_path
        out_dir = renders_root / clip_id
        narr_file = (
            Path(request.narration_path).resolve() if request.narration_path else None
        )

        resolved_modes = request.modes
        if not resolved_modes:
            resolved_modes = [
                request.crop_preset or "third_person",
            ]

        clean_modes: list[str] = []
        for m in resolved_modes:
            if m not in clean_modes and m in (
                "landscape",
                "vertical_blur",
                "third_person",
                "direct_crop",
                "cinematic",
                "custom",
                "vertical_crop",
            ):
                clean_modes.append(m)
        if not clean_modes:
            clean_modes = [request.crop_preset or "third_person"]

        job_id = uuid.uuid4()
        job = RenderJob(
            id=str(job_id),
            clip_id=clip_id,
            video_id=request.video_id,
            status="pending",
            progress=0.0,
            start_seconds=request.start_seconds,
            duration_seconds=request.duration_seconds,
            narration_path=str(narr_file) if narr_file else None,
            encoder=request.encoder,
            crop_preset=(
                request.crop_preset
                if request.crop_preset
                in ("third_person", "cinematic", "direct_crop", "custom")
                else "third_person"
            ),
            crop_blur_padding=(
                request.crop_blur_padding
                if request.crop_blur_padding is not None
                else 0.3333
            ),
            modes=",".join(clean_modes),
            overwrite=request.overwrite,
            normalize_audio=request.normalize_audio,
            target_lufs=request.target_lufs,
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        prefix = settings.API_PREFIX
        stream_outputs = {
            m: f"{prefix}/renders/{clip_id}/stream/{m}" for m in clean_modes
        }

        # Resolve primary crop mode stream url for backwards compatibility
        primary_crop = next(
            (
                m
                for m in clean_modes
                if m
                in (
                    "third_person",
                    "direct_crop",
                    "cinematic",
                    "custom",
                    "vertical_crop",
                )
            ),
            None,
        )
        vert_crop_stream = (
            f"{prefix}/renders/{clip_id}/stream/{primary_crop}"
            if primary_crop
            else None
        )

        if request.sync:
            RenderService.execute_render_job(job.id, db_session=db)
            db.refresh(job)
            if job.status == "failed":
                raise RuntimeError(f"Render failed: {job.error_message}")
            return RenderClipResponse(
                job_id=job.id,
                clip_id=clip_id,
                status=job.status,
                progress=job.progress,
                output_dir=job.output_dir or str(out_dir),
                landscape_path=job.landscape_path
                or (
                    f"{prefix}/renders/{clip_id}/stream/landscape"
                    if "landscape" in clean_modes
                    else None
                ),
                vertical_blur_path=job.vertical_blur_path
                or (
                    f"{prefix}/renders/{clip_id}/stream/vertical_blur"
                    if "vertical_blur" in clean_modes
                    else None
                ),
                vertical_crop_path=job.vertical_crop_path or vert_crop_stream,
                manifest_path=job.manifest_path
                or f"{prefix}/renders/{clip_id}/stream/manifest",
                encoder_used=job.encoder_used,
                render_duration_seconds=job.render_duration_seconds,
                modes=clean_modes,
                outputs=stream_outputs,
                message="Clip rendered successfully (synchronous).",
            )

        dispatched_to_celery = False
        if is_celery_broker_online():
            try:
                async_result = render_clip_celery_task.delay(job.id)
                job.celery_task_id = async_result.id
                db.commit()
                dispatched_to_celery = True
                logger.info(
                    "Dispatched render job %s (task: %s) to Celery worker",
                    job.id,
                    async_result.id,
                )
            except Exception as celery_err:
                logger.warning(
                    "Celery dispatch failed for job %s: %s, falling back to BackgroundTasks",
                    job.id,
                    celery_err,
                )

        if not dispatched_to_celery:
            logger.info(
                "Celery broker offline or dispatch skipped, dispatching render job %s to BackgroundTasks",
                job.id,
            )
            if background_tasks:
                background_tasks.add_task(execute_render_job, job.id)
            else:
                execute_render_job(job.id)

        return RenderClipResponse(
            job_id=job.id,
            clip_id=clip_id,
            status="pending",
            progress=0.0,
            output_dir=str(out_dir),
            landscape_path=f"{prefix}/renders/{clip_id}/stream/landscape"
            if "landscape" in clean_modes
            else None,
            vertical_blur_path=f"{prefix}/renders/{clip_id}/stream/vertical_blur"
            if "vertical_blur" in clean_modes
            else None,
            vertical_crop_path=vert_crop_stream,
            manifest_path=f"{prefix}/renders/{clip_id}/stream/manifest",
            modes=clean_modes,
            outputs=stream_outputs,
            message="Render job queued successfully"
            + (" via Celery" if dispatched_to_celery else " in background worker"),
        )

    @staticmethod
    def sync_celery_job_state(db: Session, job: RenderJob) -> None:
        """Sync live Celery execution status back to database record if job is in flight."""
        if job.celery_task_id and job.status in ("pending", "rendering"):
            try:
                res = celery_app.AsyncResult(job.celery_task_id)
                if res.state == "SUCCESS" and job.status != "completed":
                    job.status = "completed"
                    job.progress = 100.0
                    db.commit()
                elif res.state == "FAILURE" and job.status != "failed":
                    job.status = "failed"
                    job.error_message = str(res.result)
                    db.commit()
                elif res.state == "PROGRESS" and isinstance(res.info, dict):
                    job.progress = res.info.get("progress", job.progress)
                    db.commit()
            except Exception:
                pass

    @staticmethod
    def build_render_job_response(
        job: RenderJob, video: Video | None = None
    ) -> RenderJobResponse:
        """Construct RenderJobResponse schema from database model and related Video metadata."""
        prefix = settings.API_PREFIX
        job_modes = (
            [m.strip() for m in job.modes.split(",") if m.strip()]
            if job.modes
            else ([job.crop_preset or "third_person"])
        )
        stream_outputs = {}
        if job.status == "completed":
            for m in job_modes:
                stream_outputs[m] = f"{prefix}/renders/{job.clip_id}/stream/{m}"

        return RenderJobResponse(
            job_id=job.id,
            clip_id=job.clip_id,
            video_id=job.video_id,
            status=job.status,
            progress=job.progress,
            start_seconds=job.start_seconds,
            duration_seconds=job.duration_seconds,
            narration_path=job.narration_path,
            encoder=job.encoder or "auto",
            crop_preset=job.crop_preset or "third_person",
            crop_blur_padding=job.crop_blur_padding,
            normalize_audio=bool(job.normalize_audio)
            if job.normalize_audio is not None
            else True,
            target_lufs=job.target_lufs if job.target_lufs is not None else -14.0,
            output_dir=job.output_dir,
            landscape_path=job.landscape_path
            or (
                f"{prefix}/renders/{job.clip_id}/stream/landscape"
                if job.status == "completed" and "landscape" in job_modes
                else None
            ),
            vertical_blur_path=job.vertical_blur_path
            or (
                f"{prefix}/renders/{job.clip_id}/stream/vertical_blur"
                if job.status == "completed" and "vertical_blur" in job_modes
                else None
            ),
            vertical_crop_path=job.vertical_crop_path
            or (
                f"{prefix}/renders/{job.clip_id}/stream/vertical_crop"
                if job.status == "completed"
                else None
            ),
            manifest_path=job.manifest_path
            or (
                f"{prefix}/renders/{job.clip_id}/stream/manifest"
                if job.status == "completed"
                else None
            ),
            encoder_used=job.encoder_used,
            render_duration_seconds=job.render_duration_seconds,
            error_message=job.error_message,
            celery_task_id=job.celery_task_id,
            video_title=video.title if video else None,
            video_thumbnail_url=video.thumbnail_url if video else None,
            channel_name=video.channel_name if video else None,
            is_selected_for_upload=bool(job.is_selected_for_upload),
            selected_format=job.selected_format,
            upload_metadata=job.upload_metadata,
            modes=job_modes,
            outputs=stream_outputs,
            youtube_video_id=job.youtube_video_id,
            youtube_upload_status=job.youtube_upload_status or "not_uploaded",
            youtube_upload_progress=job.youtube_upload_progress or 0.0,
            youtube_upload_url=job.youtube_upload_url,
            youtube_uploaded_at=job.youtube_uploaded_at.isoformat()
            if job.youtube_uploaded_at
            else None,
            youtube_upload_error=job.youtube_upload_error,
            created_at=job.created_at.isoformat() if job.created_at else None,
            updated_at=job.updated_at.isoformat() if job.updated_at else None,
            completed_at=job.completed_at.isoformat() if job.completed_at else None,
            message=f"Render job is {job.status}",
        )

    @staticmethod
    def list_render_jobs(
        db: Session,
        video_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """List paginated render jobs, sync in-flight states, and enrich with video metadata."""
        query = db.query(RenderJob)
        if video_id:
            query = query.filter(RenderJob.video_id == video_id)
        if status and status != "all":
            query = query.filter(RenderJob.status == status)

        total = query.count()
        jobs = (
            query.order_by(RenderJob.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        video_ids = {j.video_id for j in jobs}
        videos_map: dict[str, Video] = {}
        if video_ids:
            videos = db.query(Video).filter(Video.id.in_(video_ids)).all()
            videos_map = {v.id: v for v in videos}

        results: list[RenderJobResponse] = []
        for job in jobs:
            RenderService.sync_celery_job_state(db=db, job=job)
            vid = videos_map.get(job.video_id)
            results.append(RenderService.build_render_job_response(job=job, video=vid))

        return {
            "items": [r.model_dump() for r in results],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    @staticmethod
    def get_render_job_by_id(db: Session, job_id: str) -> RenderJob | None:
        """Fetch a single render job by ID."""
        return db.query(RenderJob).filter(RenderJob.id == job_id).first()

    @staticmethod
    def retry_render_job(
        db: Session,
        job_id: str,
        background_tasks: BackgroundTasks | None = None,
    ) -> RenderJobResponse | None:
        """Reset a render job to pending state and re-dispatch for execution."""
        job = db.query(RenderJob).filter(RenderJob.id == job_id).first()
        if not job:
            return None

        job.status = "pending"
        job.progress = 0.0
        job.error_message = None
        db.commit()

        dispatched = False
        if is_celery_broker_online():
            try:
                res = render_clip_celery_task.delay(job.id)
                job.celery_task_id = res.id
                db.commit()
                dispatched = True
            except Exception:
                pass

        if not dispatched:
            if background_tasks:
                background_tasks.add_task(execute_render_job, job.id)
            else:
                execute_render_job(job.id)

        return RenderService.get_render_status(db=db, target_id=job.id)

    @staticmethod
    def update_render_job(
        db: Session,
        job_id: str,
        request: RenderJobUpdateRequest,
    ) -> RenderJobResponse | None:
        """Update fields on an existing RenderJob record."""
        job = (
            db.query(RenderJob)
            .filter((RenderJob.id == job_id) | (RenderJob.clip_id == job_id))
            .first()
        )
        if not job:
            return None

        update_data = request.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(job, field, value)

        job.updated_at = datetime.now(UTC)
        if job.status == "completed" and not job.completed_at:
            job.completed_at = datetime.now(UTC)

        db.commit()
        db.refresh(job)

        return RenderService.get_render_status(db=db, target_id=job.id)

    @staticmethod
    def delete_render_job(db: Session, job_id: str) -> dict[str, Any] | None:
        """Delete a render job by ID, including disk files and DB records."""
        return RenderService.delete_render(db=db, clip_id=job_id)

    @staticmethod
    def get_render_status(db: Session, target_id: str) -> RenderJobResponse | None:
        """Resolve render job status by job_id or clip_id, with fallback to disk manifest."""
        job = db.query(RenderJob).filter(RenderJob.id == target_id).first()
        if not job:
            job = (
                db.query(RenderJob)
                .filter(RenderJob.clip_id == target_id)
                .order_by(RenderJob.created_at.desc())
                .first()
            )

        prefix = settings.API_PREFIX

        if not job:
            renders_root = settings.renders_path
            manifest_file = renders_root / target_id / "manifest.json"
            if manifest_file.exists():
                try:
                    with open(manifest_file) as f:
                        manifest = json.load(f)
                    clip_data = manifest.get("request", {}) or manifest.get("clip", {})
                    vid_id = (
                        manifest.get("source_metadata", {}).get("video_id")
                        or manifest.get("video_id")
                        or target_id
                    )
                    vid = db.query(Video).filter(Video.id == vid_id).first()
                    return RenderJobResponse(
                        job_id=f"manifest_{target_id}",
                        clip_id=target_id,
                        video_id=vid_id,
                        status="completed",
                        progress=100.0,
                        start_seconds=clip_data.get("start_seconds", 0.0),
                        duration_seconds=clip_data.get("duration_seconds", 0.0),
                        output_dir=str(renders_root / target_id),
                        landscape_path=f"{prefix}/renders/{target_id}/stream/landscape",
                        vertical_blur_path=f"{prefix}/renders/{target_id}/stream/vertical_blur",
                        vertical_crop_path=f"{prefix}/renders/{target_id}/stream/vertical_crop",
                        manifest_path=f"{prefix}/renders/{target_id}/stream/manifest",
                        encoder_used=manifest.get("encoder"),
                        render_duration_seconds=manifest.get("render_stats", {}).get(
                            "total_render_seconds"
                        ),
                        video_title=vid.title if vid else None,
                        video_thumbnail_url=vid.thumbnail_url if vid else None,
                        channel_name=vid.channel_name if vid else None,
                        message="Render completed (recovered from manifest)",
                    )
                except Exception as e:
                    logger.warning("Failed parsing manifest for status: %s", e)
            return None

        RenderService.sync_celery_job_state(db=db, job=job)
        vid = db.query(Video).filter(Video.id == job.video_id).first()
        return RenderService.build_render_job_response(job=job, video=vid)

    @staticmethod
    def list_renders(db: Session, video_id: str | None = None) -> list[dict[str, Any]]:
        """List all completed clip renders on disk, enriched with video metadata and DB selection states."""
        renders_root = settings.renders_path
        if not renders_root.exists():
            return []

        videos = db.query(Video).all()
        video_map = {v.id: v for v in videos}

        jobs = db.query(RenderJob).all()
        job_map = {j.clip_id: j for j in jobs}

        clips = []
        for d in sorted(
            renders_root.iterdir(),
            key=lambda p: p.stat().st_mtime if p.exists() else 0,
            reverse=True,
        ):
            if d.is_dir() and (d / "manifest.json").exists():
                try:
                    with open(d / "manifest.json") as f:
                        manifest = json.load(f)

                    source_path = (
                        manifest.get("source_file")
                        or manifest.get("source", {}).get("path")
                        or ""
                    )
                    manifest_vid_id = manifest.get("source_metadata", {}).get(
                        "video_id"
                    ) or manifest.get("video_id")
                    if not manifest_vid_id:
                        if source_path:
                            manifest_vid_id = Path(source_path).stem
                        elif d.name.startswith("clip_"):
                            parts = d.name.split("_")
                            if len(parts) >= 2:
                                manifest_vid_id = parts[1]

                    if (
                        video_id
                        and manifest_vid_id != video_id
                        and video_id not in d.name
                    ):
                        continue

                    formatted = RenderService.format_render_manifest(
                        manifest, clip_id=d.name
                    )

                    matched_video = video_map.get(manifest_vid_id)
                    if matched_video:
                        formatted["video_id"] = matched_video.id
                        formatted["video_title"] = matched_video.title
                        formatted["video_thumbnail_url"] = matched_video.thumbnail_url
                        formatted["channel_name"] = matched_video.channel_name
                    elif manifest_vid_id:
                        formatted["video_id"] = manifest_vid_id

                    job = job_map.get(d.name)
                    if "upload_selection" not in formatted and job:
                        if job.upload_metadata:
                            try:
                                formatted["upload_selection"] = json.loads(
                                    job.upload_metadata
                                )
                            except Exception:
                                pass
                        elif job.is_selected_for_upload:
                            formatted["upload_selection"] = {
                                "is_selected": True,
                                "preferred_format": job.selected_format
                                or "vertical_blur",
                            }

                    clips.append(formatted)
                except Exception as e:
                    logger.error("Failed to read manifest file: %s", e)
                    continue

        return clips

    @staticmethod
    def delete_render(db: Session, clip_id: str) -> dict[str, Any] | None:
        """Delete rendered files from disk and remove all associated RenderJob rows from database."""
        renders_root = settings.renders_path
        clip_dir = renders_root / clip_id
        deleted_files = False
        if clip_dir.exists() and clip_dir.is_dir():
            shutil.rmtree(clip_dir)
            deleted_files = True

        jobs = (
            db.query(RenderJob)
            .filter((RenderJob.clip_id == clip_id) | (RenderJob.id == clip_id))
            .all()
        )
        deleted_jobs_count = len(jobs)
        for j in jobs:
            if not deleted_files and j.clip_id:
                alt_dir = renders_root / j.clip_id
                if alt_dir.exists() and alt_dir.is_dir():
                    shutil.rmtree(alt_dir)
                    deleted_files = True
            if not deleted_files and j.output_dir:
                out_p = Path(j.output_dir)
                if out_p.exists() and out_p.is_dir():
                    shutil.rmtree(out_p)
                    deleted_files = True
            db.delete(j)
        db.commit()

        if not deleted_files and deleted_jobs_count == 0:
            return None

        return {
            "status": "deleted",
            "clip_id": clip_id,
            "deleted_files": deleted_files,
            "deleted_jobs_count": deleted_jobs_count,
            "message": f"Successfully deleted render '{clip_id}'",
        }

    @staticmethod
    def bulk_delete_renders(db: Session, clip_ids: list[str]) -> dict[str, Any]:
        """Bulk delete rendered clips and their associated RenderJob records from disk and DB."""
        renders_root = settings.renders_path
        deleted_clip_ids: list[str] = []
        failed_clip_ids: list[str] = []
        not_found_clip_ids: list[str] = []

        for cid in clip_ids:
            try:
                clip_dir = renders_root / cid
                deleted_files = False
                if clip_dir.exists() and clip_dir.is_dir():
                    shutil.rmtree(clip_dir)
                    deleted_files = True

                jobs = (
                    db.query(RenderJob)
                    .filter((RenderJob.clip_id == cid) | (RenderJob.id == cid))
                    .all()
                )
                deleted_jobs_count = len(jobs)
                for j in jobs:
                    db.delete(j)

                if deleted_files or deleted_jobs_count > 0:
                    deleted_clip_ids.append(cid)
                else:
                    not_found_clip_ids.append(cid)
            except Exception as e:
                logger.error("Failed to delete render %s: %s", cid, e)
                failed_clip_ids.append(cid)

        try:
            db.commit()
        except Exception as commit_err:
            logger.error("Failed to commit bulk delete transaction: %s", commit_err)
            db.rollback()

        return {
            "deleted_clip_ids": deleted_clip_ids,
            "failed_clip_ids": failed_clip_ids,
            "not_found_clip_ids": not_found_clip_ids,
            "deleted_count": len(deleted_clip_ids),
            "total_requested": len(clip_ids),
            "message": f"Successfully deleted {len(deleted_clip_ids)} of {len(clip_ids)} render(s)",
        }

    @staticmethod
    def update_upload_selection(
        db: Session, clip_id: str, request: UploadSelectionRequest
    ) -> dict[str, Any]:
        """Update upload/publish selection details in manifest.json and RenderJob database table."""
        renders_root = settings.renders_path
        manifest_file = renders_root / clip_id / "manifest.json"

        job = (
            db.query(RenderJob)
            .filter((RenderJob.clip_id == clip_id) | (RenderJob.id == clip_id))
            .first()
        )

        existing_meta: dict[str, Any] = {}
        manifest_data: dict[str, Any] = {}
        if manifest_file.exists():
            try:
                with open(manifest_file) as f:
                    manifest_data = json.load(f)
                existing_meta = manifest_data.get("upload_selection") or {}
            except Exception as e:
                logger.warning(
                    "Could not read manifest.json for upload_selection: %s", e
                )

        if not existing_meta and job and job.upload_metadata:
            try:
                existing_meta = json.loads(job.upload_metadata)
            except Exception:
                pass

        video = (
            db.query(Video).filter(Video.id == job.video_id).first()
            if job and job.video_id
            else None
        )

        # 1. Resolve Title (ensure it never falls back to null)
        if request.title is not None and request.title.strip():
            final_title = request.title.strip()
        elif existing_meta.get("title"):
            final_title = str(existing_meta["title"]).strip()
        elif video and video.title:
            start_s = (
                int(job.start_seconds) if job and job.start_seconds is not None else 0
            )
            dur_s = (
                int(job.duration_seconds)
                if job and job.duration_seconds is not None
                else 15
            )
            final_title = (
                f"{video.title[:50]} - Highlight ({start_s}s-{start_s + dur_s}s)"
            )
        else:
            final_title = f"Gameplay Highlight - {clip_id}"

        # 2. Resolve Description (dynamic default when not staged/user-supplied)
        if request.description is not None and request.description.strip():
            final_description = request.description.strip()
        elif existing_meta.get("description"):
            final_description = str(existing_meta["description"]).strip()
        else:
            final_description = build_description(
                video, job, clip_id, is_short=False
            )

        # 3. Resolve Tags (dynamic default when not staged/user-supplied)
        if request.tags is not None and len(request.tags) > 0:
            final_tags = [t.strip() for t in request.tags if t and t.strip()]
        elif existing_meta.get("tags") and len(existing_meta["tags"]) > 0:
            final_tags = [t.strip() for t in existing_meta["tags"] if t and t.strip()]
        else:
            final_tags = build_tags(video, job, is_short=False)

        # 4. Resolve Privacy (default to public)
        final_privacy = request.privacy or existing_meta.get("privacy") or "public"
        if final_privacy not in ("private", "unlisted", "public"):
            final_privacy = "public"

        # 5. Resolve Format
        final_format = (
            request.preferred_format
            or (job.selected_format if job else None)
            or existing_meta.get("preferred_format")
            or "vertical_blur"
        )

        upload_dict = {
            "is_selected": request.is_selected,
            "preferred_format": final_format,
            "title": final_title,
            "description": final_description,
            "tags": final_tags,
            "privacy": final_privacy,
            "updated_at": datetime.now(UTC).isoformat(),
        }

        if manifest_file.exists():
            try:
                manifest_data["upload_selection"] = upload_dict
                with open(manifest_file, "w") as f:
                    json.dump(manifest_data, f, indent=2)
            except Exception as e:
                logger.warning("Could not update manifest.json upload_selection: %s", e)

        if job:
            job.is_selected_for_upload = request.is_selected
            job.selected_format = final_format
            job.upload_metadata = json.dumps(upload_dict)
            db.commit()

        return {
            "clip_id": clip_id,
            "upload_selection": upload_dict,
            "message": "Upload selection updated successfully",
        }

    @staticmethod
    def get_render_manifest(clip_id: str) -> dict[str, Any] | None:
        """Fetch and format manifest.json for a rendered clip."""
        renders_root = settings.renders_path
        manifest_file = renders_root / clip_id / "manifest.json"
        if not manifest_file.exists():
            return None

        with open(manifest_file) as f:
            manifest = json.load(f)
        return RenderService.format_render_manifest(manifest, clip_id=clip_id)

    @staticmethod
    def get_manifest_file_path(clip_id: str) -> Path | None:
        """Retrieve path to manifest.json file if it exists."""
        manifest_file = settings.renders_path / clip_id / "manifest.json"
        return manifest_file if manifest_file.exists() else None

    @staticmethod
    def get_stream_file_info(clip_id: str, video_type: str) -> tuple[Path, str, str]:
        """
        Validate video stream type and resolve file path, media type, and filename.
        Raises ValueError if video_type is invalid.
        Raises FileNotFoundError if media file is missing.
        """
        valid_types = (
            "landscape",
            "vertical_blur",
            "vertical_crop",
            "third_person",
            "direct_crop",
            "cinematic",
            "custom",
            "manifest",
        )
        if video_type not in valid_types:
            raise ValueError(
                f"Invalid video type '{video_type}'. Must be one of {valid_types}."
            )

        renders_root = settings.renders_path
        if video_type == "manifest":
            target_path = renders_root / clip_id / "manifest.json"
            media_type = "application/json"
            filename = f"{clip_id}_manifest.json"
        else:
            target_path = renders_root / clip_id / f"{video_type}.mp4"
            # Fallback for vertical_crop if vertical_crop.mp4 is not present but a specific preset is
            if video_type == "vertical_crop" and not target_path.exists():
                for alt in ("third_person", "direct_crop", "cinematic", "custom"):
                    candidate = renders_root / clip_id / f"{alt}.mp4"
                    if candidate.exists():
                        target_path = candidate
                        break

            media_type = "video/mp4"
            filename = f"{clip_id}_{video_type}.mp4"

        if not target_path.exists():
            raise FileNotFoundError(
                f"File not found: {target_path.name} in clip {clip_id}"
            )

        return target_path, media_type, filename

    @staticmethod
    def execute_render_job(
        job_id: str,
        celery_task_instance=None,
        db_session: Session | None = None,
    ) -> dict[str, Any]:
        """Core clip rendering execution logic shared by Celery and background workers."""
        is_external_session = db_session is not None
        db = db_session if db_session is not None else get_task_db_session()
        job = None
        try:
            job = RenderService.get_render_job_by_id(db, job_id)
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

            # Resolve source video file via RenderService
            source_file = RenderService.resolve_source_video_file(db, job.video_id)
            if not source_file or not source_file.exists():
                raise FileNotFoundError(
                    f"Local video file not found for video ID '{job.video_id}'. Download the VOD first."
                )

            out_dir = settings.renders_path / job.clip_id
            narr_file = (
                Path(job.narration_path).resolve() if job.narration_path else None
            )

            config = RenderConfig(
                preferred_encoder=job.encoder,
                crop_preset=job.crop_preset
                if job.crop_preset
                in ("third_person", "cinematic", "direct_crop", "custom")
                else "third_person",
                crop_blur_padding=job.crop_blur_padding
                if job.crop_blur_padding is not None
                else 0.3333,
                normalize_audio=bool(job.normalize_audio)
                if job.normalize_audio is not None
                else True,
                target_lufs=job.target_lufs if job.target_lufs is not None else -14.0,
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

            job_modes = (
                [m.strip() for m in job.modes.split(",") if m.strip()]
                if job.modes
                else None
            )

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
                modes=job_modes,
                progress_callback=on_progress,
                normalize_audio=bool(job.normalize_audio)
                if job.normalize_audio is not None
                else True,
                target_lufs=job.target_lufs if job.target_lufs is not None else -14.0,
            )

            prefix = settings.API_PREFIX
            if result.clamped and result.effective_duration_seconds > 0:
                job.duration_seconds = result.effective_duration_seconds
            job.status = "completed"
            job.progress = 100.0
            job.output_dir = str(out_dir)
            job.landscape_path = result.landscape_path or None
            job.vertical_blur_path = result.vertical_blur_path or None
            job.vertical_crop_path = result.vertical_crop_path or None
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


def execute_render_job(
    job_id: str,
    celery_task_instance=None,
    db_session: Session | None = None,
) -> dict[str, Any]:
    """Execute clip rendering job via RenderService."""
    return RenderService.execute_render_job(
        job_id=job_id,
        celery_task_instance=celery_task_instance,
        db_session=db_session,
    )


@celery_app.task(bind=True, name="render_clip_task")
def render_clip_celery_task(self, job_id: str):
    """Celery task for video clip rendering."""
    logger.info(
        "Celery task started: rendering job %s (task_id: %s)",
        job_id,
        self.request.id,
    )
    return RenderService.execute_render_job(job_id=job_id, celery_task_instance=self)


def execute_bulk_delete_job(
    clip_ids: list[str],
    celery_task_instance=None,
    db_session: Session | None = None,
) -> dict[str, Any]:
    """Execute bulk render deletion outside a request context."""
    db = db_session
    is_external_session = db_session is not None
    if db is None:
        db = get_task_db_session()

    try:
        result = RenderService.bulk_delete_renders(db=db, clip_ids=clip_ids)
        return result
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


@celery_app.task(bind=True, name="bulk_delete_renders_task")
def bulk_delete_renders_celery_task(self, clip_ids: list[str]):
    """Celery task for bulk deleting render clips."""
    logger.info(
        "Celery task started: bulk deleting %d renders (task_id: %s)",
        len(clip_ids),
        self.request.id,
    )
    return execute_bulk_delete_job(clip_ids=clip_ids, celery_task_instance=self)
