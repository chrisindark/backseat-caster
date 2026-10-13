"""Renders API endpoints."""

import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.responses import BaseResponse
from app.database import get_db
from app.schemas.render import (
    BulkDeleteRendersRequest,
    BulkDeleteRendersResponse,
    RenderClipRequest,
    RenderClipResponse,
    RenderJobResponse,
    RenderJobUpdateRequest,
    UploadSelectionRequest,
)
from app.services.renders import (
    RenderService,
    bulk_delete_renders_celery_task,
    execute_bulk_delete_job,
    is_celery_broker_online,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/renders", tags=["Renders"])

# Alias helper function for backwards compatibility
format_render_manifest = RenderService.format_render_manifest


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
    try:
        res_data = RenderService.create_render(
            db=db, request=request, background_tasks=background_tasks
        )
        return BaseResponse.success_response(response=res_data)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to create render job: %s", e)
        raise HTTPException(
            status_code=500, detail=f"Failed to create render job: {e!s}"
        )


@router.post(
    "/jobs",
    response_model=BaseResponse[RenderClipResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_render_job(
    request: RenderClipRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Trigger rendering of a local gameplay clip (RESTful alias for POST /renders).
    """
    return create_render(request=request, background_tasks=background_tasks, db=db)


@router.get("/jobs", response_model=BaseResponse[dict[str, Any]])
def list_render_jobs(
    video_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """
    List all render jobs from the database with pagination,
    filtering by video_id or status, and enriched with source video metadata.
    """
    try:
        data = RenderService.list_render_jobs(
            db=db, video_id=video_id, status=status, limit=limit, offset=offset
        )
        return BaseResponse.success_response(response=data)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to list render jobs: %s", e)
        raise HTTPException(
            status_code=500, detail=f"Failed to list render jobs: {e!s}"
        )


@router.post("/jobs/{job_id}/retry", response_model=BaseResponse[RenderJobResponse])
def retry_render_job(
    job_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Retry a failed or pending render job."""
    try:
        job_res = RenderService.retry_render_job(
            db=db, job_id=job_id, background_tasks=background_tasks
        )
        if not job_res:
            raise HTTPException(
                status_code=404, detail=f"Render job '{job_id}' not found"
            )
        return BaseResponse.success_response(response=job_res)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to retry render job %s: %s", job_id, e)
        raise HTTPException(
            status_code=500, detail=f"Failed to retry render job: {e!s}"
        )


@router.get("/jobs/{job_id}", response_model=BaseResponse[RenderJobResponse])
@router.get("/jobs/{job_id}/status", response_model=BaseResponse[RenderJobResponse])
def get_render_job(job_id: str, db: Session = Depends(get_db)):
    """Check processing status and progress for a specific render job."""
    try:
        status_res = RenderService.get_render_status(db=db, target_id=job_id)
        if not status_res:
            raise HTTPException(
                status_code=404,
                detail=f"Render job or clip '{job_id}' not found",
            )
        return BaseResponse.success_response(response=status_res)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to get render status for %s: %s", job_id, e)
        raise HTTPException(
            status_code=500, detail=f"Failed to get render status: {e!s}"
        )


@router.patch("/jobs/{job_id}", response_model=BaseResponse[RenderJobResponse])
@router.put("/jobs/{job_id}", response_model=BaseResponse[RenderJobResponse])
def update_render_job(
    job_id: str,
    request: RenderJobUpdateRequest,
    db: Session = Depends(get_db),
):
    """Update fields on a specific render job."""
    try:
        updated = RenderService.update_render_job(db=db, job_id=job_id, request=request)
        if not updated:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Render job '{job_id}' not found",
            )
        return BaseResponse.success_response(response=updated)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to update render job %s: %s", job_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update render job: {e!s}",
        )


@router.delete("/jobs/{job_id}", response_model=BaseResponse[dict[str, Any]])
def delete_render_job(job_id: str, db: Session = Depends(get_db)):
    """Delete a specific render job and its associated files."""
    try:
        result = RenderService.delete_render_job(db=db, job_id=job_id)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Render job '{job_id}' not found",
            )
        return BaseResponse.success_response(response=result)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to delete render job %s: %s", job_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete render job: {e!s}",
        )


@router.get("/{clip_id}/status", response_model=BaseResponse[RenderJobResponse])
def get_clip_render_status(clip_id: str, db: Session = Depends(get_db)):
    """Check status and progress for a clip by clip_id or job_id."""
    try:
        status_res = RenderService.get_render_status(db=db, target_id=clip_id)
        if not status_res:
            raise HTTPException(
                status_code=404,
                detail=f"Render job or clip '{clip_id}' not found",
            )
        return BaseResponse.success_response(response=status_res)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to get clip render status for %s: %s", clip_id, e)
        raise HTTPException(
            status_code=500, detail=f"Failed to get clip render status: {e!s}"
        )


@router.get("", response_model=BaseResponse[dict[str, Any]])
def list_renders(
    video_id: str | None = None,
    db: Session = Depends(get_db),
):
    """List all completed clip renders, optionally filtered by video_id."""
    try:
        clips = RenderService.list_renders(db=db, video_id=video_id)
        return BaseResponse.success_response(response={"items": clips})
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to list renders: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to list renders: {e!s}")


@router.post("/bulk-delete", response_model=BaseResponse[BulkDeleteRendersResponse])
@router.delete("/bulk", response_model=BaseResponse[BulkDeleteRendersResponse])
@router.delete("", response_model=BaseResponse[BulkDeleteRendersResponse])
def bulk_delete_renders(
    request: BulkDeleteRendersRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Bulk delete rendered clips and their associated database job records.
    Supports synchronous deletion or asynchronous background / Celery task dispatch.
    """
    try:
        if request.sync:
            result = RenderService.bulk_delete_renders(db=db, clip_ids=request.clip_ids)
            return BaseResponse.success_response(response=result)

        if is_celery_broker_online():
            task = bulk_delete_renders_celery_task.delay(request.clip_ids)
            return BaseResponse.success_response(
                response={
                    "deleted_clip_ids": [],
                    "failed_clip_ids": [],
                    "not_found_clip_ids": [],
                    "deleted_count": 0,
                    "total_requested": len(request.clip_ids),
                    "task_id": task.id,
                    "message": f"Dispatched bulk delete for {len(request.clip_ids)} render(s) via Celery",
                }
            )

        background_tasks.add_task(execute_bulk_delete_job, clip_ids=request.clip_ids)
        return BaseResponse.success_response(
            response={
                "deleted_clip_ids": [],
                "failed_clip_ids": [],
                "not_found_clip_ids": [],
                "deleted_count": 0,
                "total_requested": len(request.clip_ids),
                "task_id": None,
                "message": f"Queued bulk delete for {len(request.clip_ids)} render(s) in background worker",
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to execute bulk delete: %s", e)
        raise HTTPException(
            status_code=500, detail=f"Failed to execute bulk delete: {e!s}"
        )


@router.delete("/{clip_id}", response_model=BaseResponse[dict[str, Any]])
def delete_render(clip_id: str, db: Session = Depends(get_db)):
    """Delete a rendered clip directory from disk and remove associated database job records."""
    try:
        result = RenderService.delete_render(db=db, clip_id=clip_id)
        if not result:
            raise HTTPException(
                status_code=404,
                detail=f"Rendered clip or job '{clip_id}' not found",
            )
        return BaseResponse.success_response(response=result)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to delete render %s: %s", clip_id, e)
        raise HTTPException(status_code=500, detail=f"Failed to delete render: {e!s}")


@router.post("/{clip_id}/upload-selection", response_model=BaseResponse[dict[str, Any]])
@router.patch(
    "/{clip_id}/upload-selection", response_model=BaseResponse[dict[str, Any]]
)
def update_upload_selection(
    clip_id: str,
    request: UploadSelectionRequest,
    db: Session = Depends(get_db),
):
    """
    Select or deselect a rendered clip for publishing/uploading to YouTube.
    Persists preferred format, title, description, tags, privacy settings
    both to manifest.json and the RenderJob database table.
    """
    try:
        result = RenderService.update_upload_selection(
            db=db, clip_id=clip_id, request=request
        )
        return BaseResponse.success_response(response=result)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to update upload selection for %s: %s", clip_id, e)
        raise HTTPException(
            status_code=500, detail=f"Failed to update upload selection: {e!s}"
        )


@router.get("/{clip_id}/manifest")
@router.head("/{clip_id}/manifest")
def get_render_manifest_file(clip_id: str):
    """Download or stream raw manifest.json for a specific rendered clip."""
    manifest_file = RenderService.get_manifest_file_path(clip_id)
    if not manifest_file:
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
    manifest = RenderService.get_render_manifest(clip_id)
    if not manifest:
        raise HTTPException(
            status_code=404, detail=f"Rendered clip {clip_id} not found"
        )
    return BaseResponse.success_response(response=manifest)


@router.get("/{clip_id}/stream/{video_type}")
@router.head("/{clip_id}/stream/{video_type}")
def stream_clip_video(clip_id: str, video_type: str):
    """Stream or playback a specific rendered video (landscape, vertical_blur, vertical_crop) or manifest."""
    try:
        target_path, media_type, filename = RenderService.get_stream_file_info(
            clip_id=clip_id, video_type=video_type
        )
        return FileResponse(
            path=target_path,
            media_type=media_type,
            filename=filename,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
