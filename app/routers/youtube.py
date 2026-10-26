"""YouTube API Router for OAuth authentication and programmatic video & Shorts uploads."""

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.core.responses import BaseResponse
from app.database import get_db
from app.models.render_job import RenderJob
from app.models.video import Video
from app.schemas.render import RenderJobResponse
from app.schemas.youtube import (
    AutoStageRequest,
    AutoStageResponse,
    StagedClipsResponse,
    YouTubeAuthCallbackRequest,
    YouTubeAuthStatusResponse,
    YouTubeAuthUrlResponse,
    YouTubeBatchUploadResponse,
    YouTubeCredentialsRequest,
    YouTubeQuotaResponse,
    YouTubeScheduleRequest,
    YouTubeUploadRequest,
    YouTubeUploadResult,
)
from app.services.auto_stage import AutoStageService, as_utc
from app.services.llm_metadata import LLMMetadataService
from app.services.renders import RenderService
from app.services.youtube_quota import YouTubeQuotaService
from app.services.youtube_uploader import (
    YouTubeUploaderService,
    batch_upload_clips_celery_task,
    upload_clip_celery_task,
)
from app.worker import helpers


def is_celery_broker_online() -> bool:
    """Check whether Celery broker is online, delegating dynamically to helpers."""
    return helpers.is_celery_broker_online()


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/youtube", tags=["youtube"])


# -----------------------------------------------------------------------------
# OAuth Authentication Endpoints
# -----------------------------------------------------------------------------


@router.get("/auth/status", response_model=BaseResponse[YouTubeAuthStatusResponse])
def get_youtube_auth_status():
    """Retrieve current YouTube OAuth authentication status and connected channel details."""
    try:
        status_data = YouTubeUploaderService.get_auth_status()
        return BaseResponse.success_response(response=status_data)
    except Exception as e:
        logger.exception("Failed to get YouTube auth status: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to check YouTube authentication: {e!s}",
        )


@router.get("/auth/url", response_model=BaseResponse[YouTubeAuthUrlResponse])
def get_youtube_auth_url(redirect_uri: str | None = None):
    """
    Generate Google OAuth 2.0 authorization URL for connecting a YouTube account.
    Directs the user to Google consent screen requesting upload permissions.
    """
    try:
        auth_data = YouTubeUploaderService.generate_auth_url(redirect_uri=redirect_uri)
        return BaseResponse.success_response(response=auth_data)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.exception("Failed to generate YouTube auth URL: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate auth URL: {e!s}",
        )


@router.get("/auth/callback")
def handle_youtube_oauth_callback_redirect(
    code: str | None = Query(None),
    state: str | None = Query(None),
    error: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """
    Browser redirect handler for Google OAuth 2.0 callback.
    Exchanges code for tokens, saves credentials, and displays confirmation or redirects to UI.
    """
    if error:
        logger.warning("Google OAuth error callback: %s", error)
        return HTMLResponse(
            content=f"""
            <html>
                <body style="font-family: system-ui, sans-serif; background: #0f172a; color: #f87171; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0;">
                    <div style="background: #1e293b; padding: 2.5rem; border-radius: 1rem; border: 1px solid #ef4444; text-align: center; max-width: 500px;">
                        <h2 style="color: #ef4444; margin-top: 0;">YouTube Authorization Failed</h2>
                        <p>{error}</p>
                        <a href="http://localhost:3000" style="color: #38bdf8; text-decoration: none; font-weight: bold;">Return to BackseatCaster</a>
                    </div>
                </body>
            </html>
            """,
            status_code=400,
        )

    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing 'code' query parameter in callback.",
        )

    try:
        channel_info = YouTubeUploaderService.exchange_code(code=code, state=state)
        channel_name = channel_info.get("channel_title", "YouTube Account")
        return HTMLResponse(
            content=f"""
            <html>
                <head>
                    <title>YouTube Connected</title>
                    <meta http-equiv="refresh" content="3;url=http://localhost:3000?youtube_auth=success" />
                </head>
                <body style="font-family: system-ui, sans-serif; background: #090d16; color: #e2e8f0; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0;">
                    <div style="background: #131b2e; padding: 2.5rem; border-radius: 1.25rem; border: 1px solid rgba(255,255,255,0.1); text-align: center; max-width: 480px; box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5);">
                        <div style="font-size: 3rem; margin-bottom: 1rem;">🎉</div>
                        <h2 style="color: #f43f5e; margin: 0 0 0.5rem 0;">YouTube Connected!</h2>
                        <p style="color: #94a3b8; font-size: 0.95rem; margin-bottom: 1.5rem;">
                            Successfully authenticated as <strong>{channel_name}</strong>. You can now upload videos and Shorts programmatically.
                        </p>
                        <a href="http://localhost:3000?youtube_auth=success" style="display: inline-block; background: #e11d48; color: white; padding: 0.75rem 1.5rem; border-radius: 0.75rem; text-decoration: none; font-weight: 600; font-size: 0.9rem;">
                            Return to BackseatCaster
                        </a>
                        <p style="color: #64748b; font-size: 0.75rem; margin-top: 1rem;">Redirecting in 3 seconds...</p>
                    </div>
                </body>
            </html>
            """
        )
    except Exception as e:
        logger.exception("Failed to exchange OAuth code: %s", e)
        return HTMLResponse(
            content=f"""
            <html>
                <body style="font-family: system-ui, sans-serif; background: #0f172a; color: #f87171; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0;">
                    <div style="background: #1e293b; padding: 2.5rem; border-radius: 1rem; border: 1px solid #ef4444; text-align: center; max-width: 500px;">
                        <h2 style="color: #ef4444; margin-top: 0;">Authentication Error</h2>
                        <p>{e!s}</p>
                        <a href="http://localhost:3000" style="color: #38bdf8; text-decoration: none; font-weight: bold;">Return to BackseatCaster</a>
                    </div>
                </body>
            </html>
            """,
            status_code=500,
        )


@router.post("/auth/callback", response_model=BaseResponse[dict[str, Any]])
def exchange_oauth_code_json(request: YouTubeAuthCallbackRequest):
    """Programmatic API endpoint to exchange authorization code for credentials."""
    try:
        channel_info = YouTubeUploaderService.exchange_code(
            code=request.code,
            redirect_uri=request.redirect_uri,
            state=request.state,
            code_verifier=request.code_verifier,
        )
        return BaseResponse.success_response(response=channel_info)
    except Exception as e:
        logger.exception("Failed to exchange OAuth code: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to exchange code: {e!s}",
        )


@router.post("/auth/credentials", response_model=BaseResponse[dict[str, Any]])
def configure_youtube_credentials(request: YouTubeCredentialsRequest):
    """
    Configure YouTube client credentials or client_secrets.json directly.
    Accepts client_secrets_json string, or client_id/client_secret/refresh_token.
    """
    try:
        if request.client_secrets_json:
            YouTubeUploaderService.save_client_secrets(request.client_secrets_json)
        elif request.client_id and request.client_secret:
            data = {
                "web": {
                    "client_id": request.client_id,
                    "client_secret": request.client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            }
            YouTubeUploaderService.save_client_secrets(data)

        # If refresh token also provided, create authorized credentials
        if request.refresh_token:
            from google.oauth2.credentials import Credentials

            client_config = YouTubeUploaderService.get_client_config() or {}
            inner = client_config.get("web") or client_config.get("installed") or {}
            cid = inner.get("client_id") or request.client_id
            csec = inner.get("client_secret") or request.client_secret

            creds = Credentials(
                None,
                refresh_token=request.refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=cid,
                client_secret=csec,
                scopes=[
                    "https://www.googleapis.com/auth/youtube.upload",
                    "https://www.googleapis.com/auth/youtube.readonly",
                ],
            )
            YouTubeUploaderService.save_credentials(creds)

        status_res = YouTubeUploaderService.get_auth_status()
        return BaseResponse.success_response(
            response={
                "message": "Credentials configured successfully",
                "auth_status": status_res.model_dump(),
            }
        )
    except Exception as e:
        logger.exception("Failed to configure YouTube credentials: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to configure credentials: {e!s}",
        )


@router.post("/auth/revoke", response_model=BaseResponse[dict[str, Any]])
def revoke_youtube_credentials():
    """Disconnect and revoke YouTube OAuth authorization."""
    try:
        revoked = YouTubeUploaderService.revoke_credentials()
        return BaseResponse.success_response(
            response={
                "revoked": revoked,
                "message": "YouTube credentials disconnected successfully.",
            }
        )
    except Exception as e:
        logger.exception("Failed to revoke YouTube credentials: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to revoke credentials: {e!s}",
        )


# -----------------------------------------------------------------------------
# Video & Shorts Upload Endpoints
# -----------------------------------------------------------------------------


@router.get("/upload/queue", response_model=BaseResponse[dict[str, Any]])
@router.get("/queue", response_model=BaseResponse[dict[str, Any]])
def get_upload_queue(db: Session = Depends(get_db)):
    """Retrieve all clips staged or in-progress for YouTube upload."""
    jobs = (
        db.query(RenderJob)
        .filter(
            (RenderJob.is_selected_for_upload.is_(True))
            | (RenderJob.youtube_upload_status.in_(["uploading", "completed"]))
        )
        .order_by(RenderJob.updated_at.desc())
        .all()
    )

    items = [RenderService.build_render_job_response(job=j).model_dump() for j in jobs]

    return BaseResponse.success_response(
        response={
            "items": items,
            "total": len(items),
        }
    )


@router.post(
    "/upload/selected", response_model=BaseResponse[YouTubeBatchUploadResponse]
)
def upload_selected_queue(
    background_tasks: BackgroundTasks,
    sync: bool = Query(False, description="Whether to wait for uploads synchronously"),
    db: Session = Depends(get_db),
):
    """Upload all completed clips currently staged/selected for upload."""
    auth_status = YouTubeUploaderService.get_auth_status()
    if not auth_status.is_authenticated:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="YouTube account not authenticated. Please authenticate first via /api/v1/youtube/auth/url",
        )

    selected_jobs = (
        db.query(RenderJob)
        .filter(
            RenderJob.is_selected_for_upload.is_(True),
            RenderJob.status == "completed",
        )
        .all()
    )

    if not selected_jobs:
        return BaseResponse.success_response(
            response=YouTubeBatchUploadResponse(
                total_requested=0,
                total_succeeded=0,
                total_failed=0,
                results=[],
                message="No clips are currently selected for upload.",
            )
        )

    # Quota usage is advisory: uploads are never blocked locally so an
    # exhausted budget surfaces as YouTube's own quotaExceeded error instead.

    if sync:
        results = YouTubeUploaderService.upload_selected_clips(db=db)
        succeeded = sum(1 for r in results if r.status == "completed")
        failed = sum(1 for r in results if r.status == "failed")
        return BaseResponse.success_response(
            response=YouTubeBatchUploadResponse(
                total_requested=len(selected_jobs),
                total_succeeded=succeeded,
                total_failed=failed,
                results=results,
                message=f"Uploaded {succeeded} of {len(selected_jobs)} clips to YouTube.",
            )
        )

    # Queue in background / Celery
    for job in selected_jobs:
        job.youtube_upload_status = "uploading"
        job.youtube_upload_progress = 1.0
        job.youtube_upload_error = None
    db.commit()

    dispatched_celery = False
    if is_celery_broker_online():
        try:
            batch_upload_clips_celery_task.delay()
            dispatched_celery = True
            logger.info("Dispatched batch YouTube upload task to Celery")
        except Exception as celery_err:
            logger.warning("Celery dispatch failed for batch upload: %s", celery_err)

    if not dispatched_celery:
        logger.info("Dispatching batch YouTube upload to BackgroundTasks")
        background_tasks.add_task(YouTubeUploaderService.upload_selected_clips)

    results = []
    for j in selected_jobs:
        job_privacy = "public"
        if j.upload_metadata:
            try:
                meta = json.loads(j.upload_metadata)
                job_privacy = meta.get("privacy", "public")
            except Exception:
                pass
        results.append(
            YouTubeUploadResult(
                clip_id=j.clip_id,
                title=j.clip_id,
                format=j.selected_format or "vertical_blur",
                is_short=(j.selected_format or "vertical_blur")
                in ("vertical_blur", "vertical_crop"),
                status="uploading",
                privacy=job_privacy,
                progress=1.0,
            )
        )

    return BaseResponse.success_response(
        response=YouTubeBatchUploadResponse(
            total_requested=len(selected_jobs),
            total_succeeded=0,
            total_failed=0,
            results=results,
            message=f"Queued {len(selected_jobs)} clips for upload to YouTube in background.",
        )
    )


@router.post("/upload/{clip_id}", response_model=BaseResponse[YouTubeUploadResult])
def upload_clip(
    clip_id: str,
    request: YouTubeUploadRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Upload a rendered clip to YouTube as a video or Short.
    Supports asynchronous execution via Celery or BackgroundTasks,
    or synchronous execution when sync=True.
    """
    job = (
        db.query(RenderJob)
        .filter((RenderJob.clip_id == clip_id) | (RenderJob.id == clip_id))
        .first()
    )
    if not job:
        # Check if manifest exists on disk
        manifest = RenderService.get_render_manifest(clip_id)
        if not manifest:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Rendered clip '{clip_id}' not found.",
            )

    auth_status = YouTubeUploaderService.get_auth_status()
    if not auth_status.is_authenticated:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="YouTube account not authenticated. Please authenticate first via /api/v1/youtube/auth/url",
        )

    if job:
        existing = {}
        if job.upload_metadata:
            try:
                existing = json.loads(job.upload_metadata)
            except Exception:
                pass
        existing.update(
            {
                "is_selected": True,
                "preferred_format": request.format
                or existing.get("preferred_format")
                or job.selected_format
                or "vertical_blur",
                "title": request.title or existing.get("title"),
                "description": request.description or existing.get("description"),
                "tags": request.tags
                if request.tags is not None
                else existing.get("tags", []),
                "privacy": request.privacy or existing.get("privacy", "public"),
                "updated_at": datetime.now(UTC).isoformat(),
            }
        )
        job.upload_metadata = json.dumps(existing)
        if request.format:
            job.selected_format = request.format
        db.commit()

    if request.sync:
        try:
            result = YouTubeUploaderService.upload_clip_to_youtube(
                clip_id=clip_id,
                title=request.title,
                description=request.description,
                tags=request.tags,
                privacy=request.privacy,
                format_override=request.format,
                is_short=request.is_short,
                category_id=request.category_id,
                publish_at=request.publish_at,
                db_session=db,
            )
            return BaseResponse.success_response(response=result)
        except Exception as e:
            logger.exception("Synchronous YouTube upload failed for %s", clip_id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"YouTube upload failed: {e!s}",
            )

    # Asynchronous execution
    if job:
        job.youtube_upload_status = "uploading"
        job.youtube_upload_progress = 1.0
        job.youtube_upload_error = None
        db.commit()

    dispatched_celery = False
    if is_celery_broker_online():
        try:
            upload_clip_celery_task.delay(
                clip_id,
                request.title,
                request.description,
                request.tags,
                request.privacy,
                request.format,
                request.is_short,
                request.category_id,
                request.publish_at.isoformat() if request.publish_at else None,
            )
            dispatched_celery = True
            logger.info("Dispatched YouTube upload task for %s to Celery", clip_id)
        except Exception as celery_err:
            logger.warning("Celery dispatch failed for upload: %s", celery_err)

    if not dispatched_celery:
        logger.info("Dispatching YouTube upload for %s to BackgroundTasks", clip_id)
        background_tasks.add_task(
            YouTubeUploaderService.upload_clip_to_youtube,
            clip_id=clip_id,
            title=request.title,
            description=request.description,
            tags=request.tags,
            privacy=request.privacy,
            format_override=request.format,
            is_short=request.is_short,
            category_id=request.category_id,
            publish_at=request.publish_at,
        )

    format_name = (
        request.format
        or (job.selected_format if job else "vertical_blur")
        or "vertical_blur"
    )
    target_short = (
        request.is_short
        if request.is_short is not None
        else (format_name in ("vertical_blur", "vertical_crop"))
    )

    resolved_privacy = request.privacy
    if not resolved_privacy and job and job.upload_metadata:
        try:
            resolved_privacy = json.loads(job.upload_metadata).get("privacy")
        except Exception:
            pass
    if not resolved_privacy:
        resolved_privacy = "public"

    scheduled_at = request.publish_at
    if scheduled_at is None and job and job.scheduled_publish_at:
        scheduled_at = as_utc(job.scheduled_publish_at)
    if scheduled_at is not None and scheduled_at <= datetime.now(UTC):
        scheduled_at = None
    if scheduled_at is not None:
        resolved_privacy = "private"

    initial_result = YouTubeUploadResult(
        clip_id=clip_id,
        title=request.title or clip_id,
        format=format_name,
        is_short=target_short,
        status="uploading",
        privacy=resolved_privacy,
        progress=1.0,
        scheduled_publish_at=scheduled_at.isoformat() if scheduled_at else None,
    )
    return BaseResponse.success_response(response=initial_result)


# -----------------------------------------------------------------------------
# Phase 8: Quota, Auto-Stage & Native Scheduling Endpoints
# -----------------------------------------------------------------------------


def _get_render_job(db: Session, clip_id: str) -> RenderJob:
    job = (
        db.query(RenderJob)
        .filter((RenderJob.clip_id == clip_id) | (RenderJob.id == clip_id))
        .first()
    )
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rendered clip '{clip_id}' not found.",
        )
    return job


def _job_response(db: Session, job: RenderJob) -> RenderJobResponse:
    video = db.query(Video).filter(Video.id == job.video_id).first()
    return RenderService.build_render_job_response(job=job, video=video)


@router.get("/quota", response_model=BaseResponse[YouTubeQuotaResponse])
def get_youtube_quota(db: Session = Depends(get_db)):
    """Return today's YouTube Data API unit consumption and upload headroom."""
    try:
        summary = YouTubeQuotaService.get_summary(db)
        return BaseResponse.success_response(response=YouTubeQuotaResponse(**summary))
    except Exception as e:
        logger.exception("Failed to read YouTube quota usage: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read quota usage: {e!s}",
        )


@router.get("/staging", response_model=BaseResponse[StagedClipsResponse])
def list_staged_clips(db: Session = Depends(get_db)):
    """List auto-staged clips awaiting creator review or scheduled release."""
    jobs = (
        db.query(RenderJob)
        .filter(
            (RenderJob.auto_staged.is_(True))
            | (RenderJob.is_selected_for_upload.is_(True)),
            (RenderJob.youtube_upload_status.is_(None))
            | (RenderJob.youtube_upload_status != "completed"),
        )
        .order_by(RenderJob.created_at.desc())
        .all()
    )

    video_ids = {j.video_id for j in jobs if j.video_id}
    videos = (
        {v.id: v for v in db.query(Video).filter(Video.id.in_(video_ids)).all()}
        if video_ids
        else {}
    )

    items = [
        RenderService.build_render_job_response(
            job=j, video=videos.get(j.video_id)
        ).model_dump()
        for j in jobs
    ]
    quota = YouTubeQuotaResponse(**YouTubeQuotaService.get_summary(db))
    return BaseResponse.success_response(
        response=StagedClipsResponse(
            items=items,
            total=len(items),
            quota=quota,
            llm_available=LLMMetadataService.is_configured(),
        )
    )


@router.post(
    "/staging/{clip_id}/schedule", response_model=BaseResponse[RenderJobResponse]
)
def schedule_staged_clip(
    clip_id: str,
    request: YouTubeScheduleRequest,
    db: Session = Depends(get_db),
):
    """Set or clear the native YouTube publishAt timestamp for a staged clip."""
    job = _get_render_job(db, clip_id)

    publish_at = request.publish_at
    if publish_at is not None:
        if publish_at.tzinfo is None:
            publish_at = publish_at.replace(tzinfo=UTC)
        if publish_at <= datetime.now(UTC) + timedelta(minutes=1):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="publish_at must be at least one minute in the future (UTC).",
            )

    metadata: dict[str, Any] = {}
    if job.upload_metadata:
        try:
            metadata = json.loads(job.upload_metadata)
        except Exception:
            metadata = {}

    job.scheduled_publish_at = publish_at
    job.is_selected_for_upload = True
    metadata["is_selected"] = True
    metadata["scheduled_publish_at"] = (
        publish_at.isoformat() if publish_at is not None else None
    )
    if publish_at is not None:
        metadata["privacy"] = "private"
    job.upload_metadata = json.dumps(metadata)
    db.commit()
    db.refresh(job)

    return BaseResponse.success_response(response=_job_response(db, job))


@router.post(
    "/staging/{clip_id}/publish-now",
    response_model=BaseResponse[YouTubeUploadResult],
)
def publish_staged_clip_now(
    clip_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Clear any schedule and publish a staged clip immediately."""
    job = _get_render_job(db, clip_id)
    if job.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Clip '{clip_id}' is not rendered yet (status: {job.status}).",
        )

    metadata: dict[str, Any] = {}
    if job.upload_metadata:
        try:
            metadata = json.loads(job.upload_metadata)
        except Exception:
            metadata = {}
    job.scheduled_publish_at = None
    metadata["scheduled_publish_at"] = None
    metadata["privacy"] = "public"
    job.upload_metadata = json.dumps(metadata)
    job.is_selected_for_upload = True
    db.commit()

    return upload_clip(
        clip_id=clip_id,
        request=YouTubeUploadRequest(privacy="public"),
        background_tasks=background_tasks,
        db=db,
    )


@router.post("/auto-stage", response_model=BaseResponse[AutoStageResponse])
def auto_stage_video(
    request: AutoStageRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Render, enrich and schedule the top highlight candidates for a video."""
    try:
        result = AutoStageService.stage_top_candidates(
            db=db,
            video_id=request.video_id,
            top_n=request.top_n,
            min_score=request.min_score,
            clipping_mode=request.clipping_mode,
            schedule=request.schedule,
            background_tasks=background_tasks,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.exception("Auto-stage failed for video %s: %s", request.video_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Auto-stage failed: {e!s}",
        )
    return BaseResponse.success_response(response=AutoStageResponse(**result))
