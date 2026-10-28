"""Highlights API endpoints."""

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.responses import BaseResponse
from app.database import get_db
from app.schemas.highlight import (
    BatchStageHighlightsRequest,
    BatchStageHighlightsResponse,
    DeleteHighlightsResponse,
    DetectHighlightsRequest,
    DetectHighlightsResponse,
    HighlightCandidateListResponse,
    HighlightRunListResponse,
    HighlightStatusResponse,
)
from app.services.auto_stage import AutoStageService
from app.services.highlight.service import HighlightService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/videos/{video_id}/highlights", tags=["Highlights"])


@router.get("/runs", response_model=BaseResponse[HighlightRunListResponse])
def list_highlight_runs(
    video_id: str,
    db: Session = Depends(get_db),
):
    """List historical detection runs with latency and performance metrics for a video."""
    try:
        runs_res = HighlightService.list_runs(db=db, video_id=video_id)
        return BaseResponse.success_response(response=runs_res)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to fetch highlight runs for %s: %s", video_id, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/detect", response_model=BaseResponse[DetectHighlightsResponse])
def detect_highlights(
    video_id: str,
    background_tasks: BackgroundTasks,
    request: DetectHighlightsRequest | None = None,
    db: Session = Depends(get_db),
):
    """
    Trigger highlight candidate detection for a video.
    Supports game-specific profiling ('marvel_rivals') or generic single-player detection ('generic').
    Dispatches to Celery worker when online, or runs via FastAPI BackgroundTasks fallback.
    """
    try:
        result = HighlightService.detect_highlights(
            db=db,
            video_id=video_id,
            request=request,
            background_tasks=background_tasks,
        )
        return BaseResponse.success_response(response=result)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to start highlight detection for %s: %s", video_id, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status", response_model=BaseResponse[HighlightStatusResponse])
def get_highlight_status(
    video_id: str,
    db: Session = Depends(get_db),
):
    """Get the current highlight scanning progress and status."""
    try:
        status_res = HighlightService.get_status(db=db, video_id=video_id)
        return BaseResponse.success_response(response=status_res)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to fetch highlight status for %s: %s", video_id, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=BaseResponse[HighlightCandidateListResponse])
def list_highlight_candidates(
    video_id: str,
    db: Session = Depends(get_db),
):
    """List all ranked highlight candidates mined for a video."""
    try:
        candidates_res = HighlightService.list_candidates(db=db, video_id=video_id)
        return BaseResponse.success_response(response=candidates_res)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to list highlight candidates for %s: %s", video_id, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch-stage", response_model=BaseResponse[BatchStageHighlightsResponse])
def batch_stage_highlights(
    video_id: str,
    request: BatchStageHighlightsRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Render, enrich with LLM metadata, and schedule selected highlight candidates.
    Supports either explicit candidate IDs or auto-picking the top N unprocessed (left) candidates.
    Defaults to 'third_person' vertical framing and same-day catchup scheduling.
    """
    try:
        result = AutoStageService.stage_selected_candidates(
            db=db,
            video_id=video_id,
            candidate_ids=request.candidate_ids,
            top_n=request.top_n,
            min_score=request.min_score,
            clipping_mode=request.clipping_mode,
            schedule=request.schedule,
            same_day_catchup=request.same_day_catchup,
            crop_blur_padding=request.crop_blur_padding,
            normalize_audio=request.normalize_audio,
            background_tasks=background_tasks,
        )
        return BaseResponse.success_response(
            response=BatchStageHighlightsResponse(**result)
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Batch stage failed for video %s: %s", video_id, e)
        raise HTTPException(status_code=500, detail=f"Batch stage failed: {e!s}")


@router.delete("", response_model=BaseResponse[DeleteHighlightsResponse])
def delete_highlight_candidates(
    video_id: str,
    db: Session = Depends(get_db),
):
    """Delete all mined highlight candidates and preview thumbnails for a video."""
    try:
        result = HighlightService.delete_candidates(db=db, video_id=video_id)
        return BaseResponse.success_response(response=result)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            "Failed to delete highlight candidates for %s: %s", video_id, e
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{candidate_id}/thumb.jpg")
def get_candidate_thumbnail(
    video_id: str,
    candidate_id: str,
    db: Session = Depends(get_db),
):
    """Serve the JPEG preview thumbnail for a highlight candidate."""
    try:
        thumb_path = HighlightService.get_thumbnail_path(
            db=db, video_id=video_id, candidate_id=candidate_id
        )
        return FileResponse(
            path=thumb_path,
            media_type="image/jpeg",
            filename=f"{candidate_id}_thumb.jpg",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            "Failed to retrieve thumbnail for %s in video %s: %s",
            candidate_id,
            video_id,
            e,
        )
        raise HTTPException(status_code=500, detail=str(e))
