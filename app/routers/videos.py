"""Videos API endpoints."""

import logging
import subprocess
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.core.responses import BaseResponse
from app.database import get_db
from app.schemas.video import (
    DeleteVideoResponse,
    DownloadRequest,
    DownloadTaskResponse,
    SyncChannelRequest,
    SyncChannelResponse,
    VideoCreateRequest,
    VideoListRequest,
    VideoListResponse,
    VideoResponse,
    VideoStatusResponse,
    VideoStorageCleanupRequest,
    VideoStorageCleanupResponse,
    VideoUpdateRequest,
    YouTubeChannelVideosResponse,
)
from app.services.videos import VideoService

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


@router.get(
    "/youtube/channel",
    response_model=BaseResponse[YouTubeChannelVideosResponse],
)
def get_channel_youtube_videos(
    channel: str = Query(
        default=settings.DEFAULT_YOUTUBE_CHANNEL,
        description="YouTube channel handle or URL (e.g. @chrisindark)",
    ),
    limit: int = Query(20, ge=1, le=100, description="Max videos to load"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    db: Session = Depends(get_db),
):
    """
    Fetch raw YouTube videos directly from a channel without saving to database.
    Annotates each video with whether it already exists in the local database.
    """
    try:
        data = VideoService.get_channel_youtube_videos(
            db=db,
            channel_url=channel,
            limit=limit,
            offset=offset,
        )
        return BaseResponse.success_response(response=data)
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning("Invalid YouTube channel query: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.exception("Failed to fetch YouTube videos from channel: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not load YouTube channel videos: {e!s}",
        )


@router.post("/sync", response_model=BaseResponse[SyncChannelResponse])
def sync_channel_videos(request: SyncChannelRequest, db: Session = Depends(get_db)):
    """
    Sync videos to the database table (either an explicit list of selected videos,
    or fetched from the YouTube channel). Skips any video that already exists.
    """
    try:
        sync_result = VideoService.sync_channel(
            db=db,
            channel_url=request.channel_url,
            limit=request.limit,
            offset=request.offset,
            videos=request.videos,
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


@router.post(
    "", response_model=BaseResponse[VideoResponse], status_code=status.HTTP_201_CREATED
)
def create_video(request: VideoCreateRequest, db: Session = Depends(get_db)):
    """Create / register a new video in the catalog."""
    try:
        video = VideoService.create_video(db=db, request=request)
        return BaseResponse.success_response(response=video)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to create video: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create video: {e!s}",
        )


@router.get("/{video_id}", response_model=BaseResponse[VideoResponse])
def get_video(video_id: str, db: Session = Depends(get_db)):
    """Retrieve details for a specific video."""
    try:
        video = VideoService.get_video(db=db, video_id=video_id)
        if not video:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Video with id '{video_id}' not found",
            )
        return BaseResponse.success_response(response=video)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to retrieve video %s: %s", video_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve video: {e!s}",
        )


@router.patch("/{video_id}", response_model=BaseResponse[VideoResponse])
@router.put("/{video_id}", response_model=BaseResponse[VideoResponse])
def update_video(
    video_id: str,
    request: VideoUpdateRequest,
    db: Session = Depends(get_db),
):
    """Update metadata or status of an existing video in the catalog."""
    try:
        updated = VideoService.update_video(db=db, video_id=video_id, request=request)
        if not updated:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Video with id '{video_id}' not found",
            )
        return BaseResponse.success_response(response=updated)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to update video %s: %s", video_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update video: {e!s}",
        )


@router.delete("/{video_id}", response_model=BaseResponse[DeleteVideoResponse])
def delete_video(
    video_id: str,
    delete_file: bool = Query(
        True,
        description="Whether to delete local downloaded video file from disk as well",
    ),
    db: Session = Depends(get_db),
):
    """Delete a video from the catalog and database, optionally removing downloaded file."""
    try:
        result = VideoService.delete_video(
            db=db, video_id=video_id, delete_file=delete_file
        )
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Video with id '{video_id}' not found",
            )
        return BaseResponse.success_response(response=result)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to delete video %s: %s", video_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete video: {e!s}",
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
        task_response = VideoService.start_download(
            db=db,
            video_id=video_id,
            quality=request.quality,
            background_tasks=background_tasks,
        )
        if not task_response:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Video not found in catalog",
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
        result = VideoService.delete_downloaded_video(db=db, video_id=video_id)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Video not found",
            )
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


@router.post(
    "/{video_id}/cleanup",
    response_model=BaseResponse[VideoStorageCleanupResponse],
)
def cleanup_video_storage(
    video_id: str,
    request: VideoStorageCleanupRequest = VideoStorageCleanupRequest(),
    db: Session = Depends(get_db),
):
    """
    Clean up local storage for a processed video (source VOD and/or uploaded render folders).
    Reclaims disk space safely while preserving catalog metadata and YouTube upload records.
    """
    try:
        result = VideoService.cleanup_video_storage(
            db=db,
            video_id=video_id,
            clean_vod=request.clean_vod,
            clean_uploaded_renders=request.clean_uploaded_renders,
            clean_all_renders=request.clean_all_renders,
        )
        return BaseResponse.success_response(response=result)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to cleanup video storage %s: %s", video_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cleanup video storage: {e!s}",
        )


@router.get("/{video_id}/stream")
@router.head("/{video_id}/stream")
def stream_video(video_id: str, db: Session = Depends(get_db)):
    """
    Stream or playback a downloaded source video with HTTP Range request support.
    Allows seeking to any timestamp for preview and clipping in the frontend modal.
    """
    try:
        video = VideoService.get_video_by_id(db=db, video_id=video_id)
        if not video:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Video with id '{video_id}' not found",
            )

        file_info = VideoService.get_video_file_info(db=db, video_id=video_id)
        if not file_info:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Downloaded video file for '{video_id}' not found on disk",
            )

        target_path, media_type, filename = file_info
        return FileResponse(
            path=target_path,
            media_type=media_type,
            filename=filename,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to stream video %s: %s", video_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to stream video: {e!s}",
        )


@router.post(
    "/upload",
    response_model=BaseResponse[VideoResponse],
    status_code=status.HTTP_201_CREATED,
)
def upload_local_video(
    file: UploadFile = File(...),
    title: str | None = Form(None),
    channel_name: str | None = Form("OBS Studio"),
    db: Session = Depends(get_db),
):
    """Directly upload and ingest an OBS or local gameplay recording (.mp4, .mkv, .mov, .webm, etc.)."""
    try:
        video_res = VideoService.upload_local_video(
            db=db,
            file=file,
            title=title,
            channel_name=channel_name,
        )
        return BaseResponse.success_response(
            response=video_res,
            status_code=status.HTTP_201_CREATED,
        )
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve),
        )
    except Exception as e:
        logger.exception("Failed to upload local video: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload local video: {e!s}",
        )


@router.get("/{video_id}/thumbnail")
def get_video_thumbnail(video_id: str, db: Session = Depends(get_db)):
    """Serve or extract on-demand thumbnail image for a local or downloaded video."""
    thumb_path = settings.downloads_path / f"{video_id}_thumb.jpg"
    if thumb_path.exists() and thumb_path.stat().st_size > 0:
        return FileResponse(path=thumb_path, media_type="image/jpeg")

    file_info = VideoService.get_video_file_info(db=db, video_id=video_id)
    if file_info:
        target_path, _, _ = file_info
        try:
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-ss",
                    "0.5",
                    "-i",
                    str(target_path),
                    "-vframes",
                    "1",
                    "-q:v",
                    "2",
                    str(thumb_path),
                ],
                capture_output=True,
                check=False,
                timeout=10,
            )
            if thumb_path.exists() and thumb_path.stat().st_size > 0:
                return FileResponse(path=thumb_path, media_type="image/jpeg")
        except Exception as e:
            logger.warning(
                "Failed on-demand thumbnail generation for %s: %s", video_id, e
            )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Thumbnail not found for video '{video_id}'",
    )
