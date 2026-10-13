"""Highlights API endpoints."""

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.responses import BaseResponse
from app.database import get_db
from app.schemas.highlight import (
    DeleteHighlightsResponse,
    DetectHighlightsRequest,
    DetectHighlightsResponse,
    HighlightCandidateListResponse,
    HighlightRunListResponse,
    HighlightStatusResponse,
)
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
