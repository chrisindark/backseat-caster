"""First-run setup wizard & runtime configuration router."""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.responses import BaseResponse
from app.database import get_db
from app.schemas.setup import (
    DemoProjectRequest,
    DemoProjectResponse,
    SetupSettingsResponse,
    SetupStatusResponse,
    UpdateSetupSettingsRequest,
)
from app.services.setup import SetupService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/setup", tags=["Setup & Diagnostics"])


@router.get("/status", response_model=BaseResponse[SetupStatusResponse])
def get_setup_status(db: Session = Depends(get_db)):
    """
    Get 4-point setup health status: FFmpeg, Disk Space, AI Key, and YouTube.
    Surfaces actionable diagnostics and overall readiness for the web UI wizard.
    """
    try:
        report = SetupService.get_status(db)
        return BaseResponse.success_response(response=report)
    except Exception as e:
        logger.exception("Failed evaluating setup status: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed evaluating setup status: {e!s}",
        )


@router.get("/settings", response_model=BaseResponse[SetupSettingsResponse])
def get_runtime_settings():
    """Get active in-app settings configurable without editing .env."""
    try:
        data = SetupService.get_settings()
        return BaseResponse.success_response(response=data)
    except Exception as e:
        logger.exception("Failed loading runtime settings: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed loading runtime settings: {e!s}",
        )


@router.patch("/settings", response_model=BaseResponse[SetupSettingsResponse])
def update_runtime_settings(request: UpdateSetupSettingsRequest):
    """Update runtime settings and persist them to data/settings.json."""
    try:
        updated = SetupService.update_settings(request)
        return BaseResponse.success_response(response=updated)
    except Exception as e:
        logger.exception("Failed saving runtime settings: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed saving runtime settings: {e!s}",
        )


@router.post("/demo", response_model=BaseResponse[DemoProjectResponse])
def load_sample_demo_project(
    request: DemoProjectRequest | None = None,
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
):
    """
    Seed a 60-second Marvel Rivals highlight demo project and render 3 Shorts.
    Gives new users an immediate, interactive experience in < 30 seconds.
    """
    req = request or DemoProjectRequest()
    try:
        result = SetupService.load_demo_project(
            db=db,
            auto_render=req.auto_render,
            sync=req.sync,
            background_tasks=background_tasks,
        )
        return BaseResponse.success_response(response=result)
    except Exception as e:
        logger.exception("Failed creating demo project: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed creating demo project: {e!s}",
        )
