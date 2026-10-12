import json
import logging
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.core.responses import BaseResponse
from app.database import get_db
from app.models.render_job import RenderJob
from app.models.video import Video
from app.schemas.render import RenderClipRequest, RenderClipResponse, RenderJobResponse
from app.worker.celery_app import celery_app
from app.worker.helpers import is_celery_broker_online
from app.worker.tasks import execute_render_job, render_clip_celery_task

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/renders", tags=["Renders"])


@router.post("", response_model=BaseResponse[RenderClipResponse])
def create_render(
    request: RenderClipRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Trigger rendering of a local gameplay clip into:
    - landscape.mp4 (1920x1080)
    - vertical_blur.mp4 (1080x1920 blurred top/bottom)
    - vertical_crop.mp4 (1080x1920 with configurable third-person or direct crop layout)
    - manifest.json

    Dispatches to Celery worker when online, or runs via FastAPI BackgroundTasks fallback.
    """
    # 1. Resolve source video from database or local downloads folder
    video = db.query(Video).filter(Video.id == request.video_id).first()
    source_file = None

    if video and video.local_file_path and Path(video.local_file_path).exists():
        source_file = Path(video.local_file_path)
    else:
        # Check directly in downloads directory
        matches = list(settings.downloads_path.glob(f"{request.video_id}.*"))
        if matches:
            source_file = matches[0]

    if not source_file or not source_file.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Local video file not found for ID: {request.video_id}. Download the VOD first.",
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

    # 2. Persist RenderJob record in database
    job_id = f"render_{uuid.uuid4().hex[:12]}"
    job = RenderJob(
        id=job_id,
        clip_id=clip_id,
        video_id=request.video_id,
        status="pending",
        progress=0.0,
        start_seconds=request.start_seconds,
        duration_seconds=request.duration_seconds,
        narration_path=str(narr_file) if narr_file else None,
        encoder=request.encoder,
        crop_preset=request.crop_preset
        if request.crop_preset in ("third_person", "cinematic", "direct_crop", "custom")
        else "third_person",
        crop_blur_padding=request.crop_blur_padding
        if request.crop_blur_padding is not None
        else 0.3333,
        overwrite=request.overwrite,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    prefix = settings.API_PREFIX

    # 3. Synchronous execution if explicitly requested
    if request.sync:
        res = execute_render_job(job.id)
        db.refresh(job)
        if job.status == "failed":
            raise HTTPException(
                status_code=400, detail=f"Render failed: {job.error_message}"
            )
        res_data = RenderClipResponse(
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
        return BaseResponse.success_response(response=res_data)

    # 4. Asynchronous dispatch: Celery if broker online, else FastAPI BackgroundTasks
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
        background_tasks.add_task(execute_render_job, job.id)

    res_data = RenderClipResponse(
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
    return BaseResponse.success_response(response=res_data)


@router.get("/jobs/{job_id}", response_model=BaseResponse[RenderJobResponse])
@router.get("/jobs/{job_id}/status", response_model=BaseResponse[RenderJobResponse])
def get_render_job(job_id: str, db: Session = Depends(get_db)):
    """Check processing status and progress for a specific render job."""
    return get_render_status_impl(target_id=job_id, db=db)


@router.get("/{clip_id}/status", response_model=BaseResponse[RenderJobResponse])
def get_clip_render_status(clip_id: str, db: Session = Depends(get_db)):
    """Check status and progress for a clip by clip_id or job_id."""
    return get_render_status_impl(target_id=clip_id, db=db)


def get_render_status_impl(
    target_id: str, db: Session
) -> BaseResponse[RenderJobResponse]:
    """Shared implementation for job status resolution."""
    job = db.query(RenderJob).filter(RenderJob.id == target_id).first()
    if not job:
        # Fallback to latest job with this clip_id
        job = (
            db.query(RenderJob)
            .filter(RenderJob.clip_id == target_id)
            .order_by(RenderJob.created_at.desc())
            .first()
        )

    prefix = settings.API_PREFIX

    if not job:
        # Check if completed manifest exists on disk (legacy / direct CLI renders)
        renders_root = settings.renders_path
        manifest_file = renders_root / target_id / "manifest.json"
        if manifest_file.exists():
            try:
                with open(manifest_file) as f:
                    manifest = json.load(f)
                clip_data = manifest.get("clip", {})
                resp = RenderJobResponse(
                    job_id=f"manifest_{target_id}",
                    clip_id=target_id,
                    video_id=manifest.get("source_metadata", {}).get("video_id")
                    or target_id,
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
                    message="Render completed (recovered from manifest)",
                )
                return BaseResponse.success_response(response=resp)
            except Exception as e:
                logger.warning("Failed parsing manifest for status: %s", e)

        raise HTTPException(
            status_code=404,
            detail=f"Render job or clip '{target_id}' not found",
        )

    # Sync Celery state if applicable
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

    resp = RenderJobResponse(
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
        created_at=job.created_at.isoformat() if job.created_at else None,
        updated_at=job.updated_at.isoformat() if job.updated_at else None,
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
        message=f"Render job is {job.status}",
    )
    return BaseResponse.success_response(response=resp)


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
        if "vertical_blur" in outputs and isinstance(outputs["vertical_blur"], dict):
            outputs["vertical_blur"]["path"] = vert_blur_stream
        if "vertical_crop" in outputs and isinstance(outputs["vertical_crop"], dict):
            outputs["vertical_crop"]["path"] = vert_crop_stream
        manifest["outputs"] = outputs

    if "source" not in manifest and "source_file" in manifest:
        source_meta = manifest.get("source_metadata", {})
        manifest["source"] = {
            "path": manifest.get("source_file"),
            **source_meta,
        }

    return manifest


@router.get("", response_model=BaseResponse[dict[str, Any]])
def list_renders():
    """List all completed clip renders."""
    renders_root = settings.renders_path
    if not renders_root.exists():
        return BaseResponse.success_response(response={"items": []})

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
                clips.append(format_render_manifest(manifest, clip_id=d.name))
            except Exception as e:
                logger.error("Failed to read manifest file: %s", e)
                continue

    return BaseResponse.success_response(response={"items": clips})


@router.get("/{clip_id}/manifest")
@router.head("/{clip_id}/manifest")
def get_render_manifest_file(clip_id: str):
    """Download or stream raw manifest.json for a specific rendered clip."""
    renders_root = settings.renders_path
    manifest_file = renders_root / clip_id / "manifest.json"
    if not manifest_file.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Manifest file not found for clip {clip_id}",
        )
    return FileResponse(
        path=manifest_file,
        media_type="application/json",
        filename=f"{clip_id}_manifest.json",
    )


@router.get("/{clip_id}", response_model=BaseResponse[dict[str, Any]])
def get_render(clip_id: str):
    """Get manifest and paths for a specific rendered clip."""
    renders_root = settings.renders_path
    manifest_file = renders_root / clip_id / "manifest.json"
    if not manifest_file.exists():
        raise HTTPException(
            status_code=404, detail=f"Rendered clip {clip_id} not found"
        )

    with open(manifest_file) as f:
        manifest = json.load(f)
    return BaseResponse.success_response(
        response=format_render_manifest(manifest, clip_id=clip_id)
    )


@router.get("/{clip_id}/stream/{video_type}")
@router.head("/{clip_id}/stream/{video_type}")
def stream_clip_video(clip_id: str, video_type: str):
    """Stream or playback a specific rendered video (landscape, vertical_blur, vertical_crop) or manifest."""
    valid_types = ("landscape", "vertical_blur", "vertical_crop", "manifest")
    if video_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid video type '{video_type}'. Must be 'landscape', 'vertical_blur', 'vertical_crop', or 'manifest'.",
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
        raise HTTPException(
            status_code=404,
            detail=f"File not found: {target_path.name} in clip {clip_id}",
        )
    return FileResponse(
        path=target_path,
        media_type=media_type,
        filename=filename,
    )
