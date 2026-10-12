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
    UploadSelectionRequest,
)
from app.worker.celery_app import celery_app
from app.worker.helpers import is_celery_broker_online

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
        landscape_stream = f"{prefix}/renders/{cid}/stream/landscape"
        vert_blur_stream = f"{prefix}/renders/{cid}/stream/vertical_blur"
        vert_crop_stream = f"{prefix}/renders/{cid}/stream/vertical_crop"
        manifest_stream = f"{prefix}/renders/{cid}/stream/manifest"

        manifest["landscape_path"] = landscape_stream
        manifest["vertical_blur_path"] = vert_blur_stream
        manifest["vertical_crop_path"] = vert_crop_stream
        manifest["manifest_path"] = manifest_stream

        outputs = manifest.get("outputs", {})
        if isinstance(outputs, dict):
            if "landscape" in outputs and isinstance(outputs["landscape"], dict):
                outputs["landscape"]["path"] = landscape_stream
            if "vertical_blur" in outputs and isinstance(
                outputs["vertical_blur"], dict
            ):
                outputs["vertical_blur"]["path"] = vert_blur_stream
            if "vertical_crop" in outputs and isinstance(
                outputs["vertical_crop"], dict
            ):
                outputs["vertical_crop"]["path"] = vert_crop_stream
            manifest["outputs"] = outputs

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
            overwrite=request.overwrite,
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        prefix = settings.API_PREFIX

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
                or f"{prefix}/renders/{clip_id}/stream/landscape",
                vertical_blur_path=job.vertical_blur_path
                or f"{prefix}/renders/{clip_id}/stream/vertical_blur",
                vertical_crop_path=job.vertical_crop_path
                or f"{prefix}/renders/{clip_id}/stream/vertical_crop",
                manifest_path=job.manifest_path
                or f"{prefix}/renders/{clip_id}/stream/manifest",
                encoder_used=job.encoder_used,
                render_duration_seconds=job.render_duration_seconds,
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
            landscape_path=f"{prefix}/renders/{clip_id}/stream/landscape",
            vertical_blur_path=f"{prefix}/renders/{clip_id}/stream/vertical_blur",
            vertical_crop_path=f"{prefix}/renders/{clip_id}/stream/vertical_crop",
            manifest_path=f"{prefix}/renders/{clip_id}/stream/manifest",
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
            output_dir=job.output_dir,
            landscape_path=job.landscape_path
            or (
                f"{prefix}/renders/{job.clip_id}/stream/landscape"
                if job.status == "completed"
                else None
            ),
            vertical_blur_path=job.vertical_blur_path
            or (
                f"{prefix}/renders/{job.clip_id}/stream/vertical_blur"
                if job.status == "completed"
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
                    clip_data = manifest.get("clip", {})
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
    def update_upload_selection(
        db: Session, clip_id: str, request: UploadSelectionRequest
    ) -> dict[str, Any]:
        """Update upload/publish selection details in manifest.json and RenderJob database table."""
        renders_root = settings.renders_path
        manifest_file = renders_root / clip_id / "manifest.json"
        upload_dict = {
            "is_selected": request.is_selected,
            "preferred_format": request.preferred_format,
            "title": request.title,
            "description": request.description,
            "tags": request.tags or [],
            "privacy": request.privacy or "private",
            "updated_at": datetime.now(UTC).isoformat(),
        }

        if manifest_file.exists():
            try:
                with open(manifest_file, "r") as f:
                    manifest_data = json.load(f)
                manifest_data["upload_selection"] = upload_dict
                with open(manifest_file, "w") as f:
                    json.dump(manifest_data, f, indent=2)
            except Exception as e:
                logger.warning("Could not update manifest.json upload_selection: %s", e)

        job = (
            db.query(RenderJob)
            .filter((RenderJob.clip_id == clip_id) | (RenderJob.id == clip_id))
            .first()
        )
        if job:
            job.is_selected_for_upload = request.is_selected
            job.selected_format = request.preferred_format
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
        valid_types = ("landscape", "vertical_blur", "vertical_crop", "manifest")
        if video_type not in valid_types:
            raise ValueError(
                f"Invalid video type '{video_type}'. Must be 'landscape', 'vertical_blur', 'vertical_crop', or 'manifest'."
            )

        renders_root = settings.renders_path
        if video_type == "manifest":
            target_path = renders_root / clip_id / "manifest.json"
            media_type = "application/json"
            filename = f"{clip_id}_manifest.json"
        else:
            target_path = renders_root / clip_id / f"{video_type}.mp4"
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
            job.vertical_blur_path = (
                f"{prefix}/renders/{job.clip_id}/stream/vertical_blur"
            )
            job.vertical_crop_path = (
                f"{prefix}/renders/{job.clip_id}/stream/vertical_crop"
            )
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
