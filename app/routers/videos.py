"""Videos API endpoints."""

import logging
import os
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.responses import BaseResponse
from app.database import get_db
from app.schemas.video import (
    DeleteVideoResponse,
    DownloadRequest,
    DownloadTaskResponse,
    SyncChannelRequest,
    SyncChannelResponse,
    VideoListRequest,
    VideoListResponse,
    VideoResponse,
    VideoStatusResponse,
)
from app.services.videos import VideoService
from app.worker.helpers import is_celery_broker_online
from app.worker.tasks import download_video_celery_task, execute_download_job

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/videos", tags=["Videos"])


@router.get("", response_model=BaseResponse[VideoListResponse])
def list_videos(
    request: Annotated[VideoListRequest, Query()],
    db: Session = Depends(get_db),
):
    """List paginated videos stored in the local database."""
    try:
        videos_page = VideoService.list_videos(
            db=db,
            page=request.page,
            limit=request.limit,
            status=request.status_filter,
            search=request.search,
            channel=request.channel,
        )
        return BaseResponse.success_response(response=videos_page)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to list videos: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list videos: {e!s}",
        )


@router.post("/sync", response_model=BaseResponse[SyncChannelResponse])
def sync_channel_videos(request: SyncChannelRequest, db: Session = Depends(get_db)):
    """
    Fetch the latest videos from a YouTube channel via yt-dlp
    and upsert them into the database.
    """
    try:
        sync_result = VideoService.sync_channel(
            db=db,
            channel_url=request.channel_url,
            limit=request.limit,
            offset=request.offset,
        )
        return BaseResponse.success_response(response=sync_result)
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning("Invalid sync parameter: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.exception("Failed to sync channel videos: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not fetch videos from YouTube channel: {e!s}",
        )


@router.get("/{video_id}", response_model=BaseResponse[VideoResponse])
def get_video(video_id: str, db: Session = Depends(get_db)):
    """Retrieve details for a specific video."""
    try:
        video = VideoService.get_video_by_id(db=db, video_id=video_id)
        if not video:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Video with id '{video_id}' not found",
            )
        return BaseResponse.success_response(
            response=VideoResponse.model_validate(video)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to retrieve video %s: %s", video_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve video: {e!s}",
        )


@router.post("/{video_id}/download", response_model=BaseResponse[DownloadTaskResponse])
def download_video(
    video_id: str,
    request: DownloadRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Trigger download of a video via yt-dlp.
    Dispatches to Celery if broker is available, or runs via FastAPI BackgroundTasks.
    """
    try:
        video = VideoService.get_video_by_id(db=db, video_id=video_id)
        if not video:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Video not found in catalog",
            )

        if video.download_status == "downloading":
            task_response = DownloadTaskResponse(
                video_id=video_id,
                download_status=video.download_status,
                download_progress=video.download_progress,
                local_file_path=video.local_file_path,
                message="Download is already in progress.",
            )
            return BaseResponse.success_response(response=task_response)

        if (
            video.is_downloaded
            and video.local_file_path
            and os.path.exists(video.local_file_path)
        ):
            task_response = DownloadTaskResponse(
                video_id=video_id,
                download_status="completed",
                download_progress=100.0,
                local_file_path=video.local_file_path,
                message="Video is already downloaded locally.",
            )
            return BaseResponse.success_response(response=task_response)

        # Update initial pending status via service
        VideoService.mark_download_pending(db=db, video=video)

        task_id = None
        dispatched_to_celery = False

        if is_celery_broker_online():
            logger.info("Dispatching to Celery worker for video %s", video_id)
            try:
                async_result = download_video_celery_task.delay(
                    video_id, request.quality
                )
                task_id = async_result.id
                dispatched_to_celery = True
                logger.info("Dispatched download task %s to Celery worker", task_id)
            except Exception as celery_err:
                logger.warning("Celery dispatch failed: %s", celery_err)

        if not dispatched_to_celery:
            logger.info(
                "Celery broker is not online, dispatching to background tasks for video %s",
                video_id,
            )
            background_tasks.add_task(execute_download_job, video_id, request.quality)
            task_id = f"bg-{video_id}"

        task_response = DownloadTaskResponse(
            video_id=video_id,
            download_status="pending",
            download_progress=0.0,
            task_id=task_id,
            message="Download queued successfully"
            + (" via Celery" if dispatched_to_celery else " in background worker"),
        )
        return BaseResponse.success_response(response=task_response)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to dispatch download for %s: %s", video_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initiate download: {e!s}",
        )


@router.get("/{video_id}/status", response_model=BaseResponse[VideoStatusResponse])
def get_download_status(video_id: str, db: Session = Depends(get_db)):
    """Check current download status and progress."""
    try:
        status_data = VideoService.get_download_status(db=db, video_id=video_id)
        if not status_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Video not found",
            )
        return BaseResponse.success_response(response=status_data)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to check status for %s: %s", video_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to check download status: {e!s}",
        )


@router.delete("/{video_id}/download", response_model=BaseResponse[DeleteVideoResponse])
def delete_downloaded_video(video_id: str, db: Session = Depends(get_db)):
    """Delete a downloaded video file from local disk."""
    try:
        video = VideoService.get_video_by_id(db=db, video_id=video_id)
        if not video:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Video not found",
            )

        result = VideoService.delete_downloaded_video(db=db, video=video)
        return BaseResponse.success_response(response=result)
    except HTTPException:
        raise
    except OSError as e:
        logger.exception("OS error deleting file for video %s: %s", video_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete file: {e!s}",
        )
    except Exception as e:
        logger.exception("Failed to delete video download %s: %s", video_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete video download: {e!s}",
        )
