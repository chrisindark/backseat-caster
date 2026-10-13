"""Video service containing database and business logic for video management."""

import logging
import math
import mimetypes
import os
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_task_db_session
from app.models.render_job import RenderJob
from app.models.video import Video
from app.schemas.video import (
    DeleteVideoResponse,
    DownloadTaskResponse,
    SyncChannelResponse,
    VideoBase,
    VideoCreateRequest,
    VideoListResponse,
    VideoResponse,
    VideoStatusResponse,
    VideoUpdateRequest,
    YouTubeChannelVideoItem,
    YouTubeChannelVideosResponse,
)
from app.services.youtube import YtdlpService, format_duration
from app.worker import helpers
from app.worker.celery_app import celery_app


def is_celery_broker_online() -> bool:
    """Check whether Celery broker is online, delegating dynamically to helpers."""
    return helpers.is_celery_broker_online()


logger = logging.getLogger(__name__)


class VideoService:
    """Service handling database queries and business logic for videos."""

    @staticmethod
    def get_video_by_id(db: Session, video_id: str) -> Video | None:
        """Fetch a single video from the database by its ID."""
        return db.query(Video).filter(Video.id == video_id).first()

    @staticmethod
    def get_video_file_info(db: Session, video_id: str) -> tuple[Path, str, str] | None:
        """
        Locate the local file path for a downloaded video.
        Returns a tuple of (Path, media_type, filename) or None if not found.
        """
        video = db.query(Video).filter(Video.id == video_id).first()
        if not video:
            return None

        candidate_path: Path | None = None
        if video.local_file_path and os.path.exists(video.local_file_path):
            candidate_path = Path(video.local_file_path)
        else:
            # Check in settings.downloads_path for {video_id}.mp4 or other extensions
            expected_file = settings.downloads_path / f"{video_id}.mp4"
            if expected_file.exists():
                candidate_path = expected_file
            else:
                matches = list(settings.downloads_path.glob(f"{video_id}.*"))
                video_matches = [
                    m
                    for m in matches
                    if m.suffix.lower()
                    in [".mp4", ".mkv", ".webm", ".mov", ".ts", ".m4v"]
                ]
                if video_matches:
                    candidate_path = video_matches[0]

        if not candidate_path or not candidate_path.exists():
            return None

        media_type, _ = mimetypes.guess_type(str(candidate_path))
        if not media_type:
            media_type = "video/mp4"

        return candidate_path, media_type, candidate_path.name

    @staticmethod
    def list_videos(
        db: Session,
        page: int = 1,
        limit: int = 20,
        status: str | None = None,
        search: str | None = None,
        channel: str | None = None,
    ) -> VideoListResponse:
        """
        Query paginated videos with optional search, channel, and status filters.
        Orders results with active downloads first, followed by recently updated.
        """
        query = db.query(Video)

        if search:
            search_filter = f"%{search.strip()}%"
            query = query.filter(
                or_(
                    Video.title.ilike(search_filter),
                    Video.channel_name.ilike(search_filter),
                )
            )

        if channel:
            query = query.filter(
                or_(
                    Video.channel_name.ilike(f"%{channel}%"),
                    Video.channel_url.ilike(f"%{channel}%"),
                )
            )

        if status and status != "all":
            if status in ["downloaded", "completed"]:
                query = query.filter(
                    or_(
                        Video.is_downloaded.is_(True),
                        Video.download_status == "completed",
                    )
                )
            elif status == "not_downloaded":
                query = query.filter(
                    or_(
                        Video.is_downloaded.is_(False),
                        Video.is_downloaded.is_(None),
                    ),
                    Video.download_status.notin_(
                        ["completed", "downloading", "pending"]
                    ),
                )
            elif status in ["downloading", "pending"]:
                query = query.filter(
                    Video.download_status.in_(["downloading", "pending"])
                )
            elif status == "failed":
                query = query.filter(Video.download_status == "failed")

        total = query.count()
        total_pages = math.ceil(total / limit) if total > 0 else 1

        items = (
            query.order_by(
                Video.created_at.asc(),
            )
            .offset((page - 1) * limit)
            .limit(limit)
            .all()
        )

        first_item = items[0] if items else None
        channel_title = first_item.channel_name if first_item else None
        channel_url = first_item.channel_url if first_item else None

        return VideoListResponse(
            items=[VideoResponse.model_validate(item) for item in items],
            total=total,
            page=page,
            limit=limit,
            total_pages=total_pages,
            channel_title=channel_title,
            channel_url=channel_url,
        )

    @staticmethod
    def get_channel_youtube_videos(
        db: Session,
        channel_url: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> YouTubeChannelVideosResponse:
        """
        Fetch video metadata from YouTube channel without writing to DB,
        annotating each video with its database presence and download status.
        """
        target_channel = channel_url or settings.DEFAULT_YOUTUBE_CHANNEL
        data = YtdlpService.extract_channel_metadata(
            target_channel, limit=limit, offset=offset
        )
        videos_raw = data.get("videos", [])
        video_ids = [v["id"] for v in videos_raw if v.get("id")]

        existing_map: dict[str, Video] = {}
        if video_ids:
            existing_db = db.query(Video).filter(Video.id.in_(video_ids)).all()
            existing_map = {v.id: v for v in existing_db}

        items: list[YouTubeChannelVideoItem] = []
        for raw in videos_raw:
            vid_id = raw["id"]
            existing = existing_map.get(vid_id)
            is_in_db = existing is not None
            is_dl = existing.is_downloaded if existing else False
            dl_status = existing.download_status if existing else "not_downloaded"

            items.append(
                YouTubeChannelVideoItem(
                    id=vid_id,
                    title=raw["title"],
                    description=raw.get("description"),
                    thumbnail_url=raw.get("thumbnail_url"),
                    duration=raw.get("duration", 0),
                    duration_formatted=raw.get("duration_formatted", "0:00"),
                    channel_name=raw.get("channel_name"),
                    channel_id=raw.get("channel_id"),
                    channel_url=raw.get("channel_url"),
                    view_count=raw.get("view_count", 0),
                    published_at=raw.get("published_at"),
                    webpage_url=raw.get("webpage_url"),
                    is_in_database=is_in_db,
                    is_downloaded=is_dl,
                    download_status=dl_status,
                )
            )

        channel_title = data.get("channel_title") or target_channel
        resolved_channel_url = data.get("channel_url") or target_channel

        return YouTubeChannelVideosResponse(
            channel_title=channel_title,
            channel_id=data.get("channel_id"),
            channel_url=resolved_channel_url,
            limit=limit,
            offset=offset,
            total_loaded=len(items),
            has_more=len(items) >= limit,
            videos=items,
        )

    @staticmethod
    def sync_channel(
        db: Session,
        channel_url: str | None = None,
        limit: int = 20,
        offset: int = 0,
        videos: list[VideoBase] | None = None,
    ) -> SyncChannelResponse:
        """
        Sync videos to the SQL database.
        If a video already exists in the database, it is skipped.
        If an explicit list of videos is provided, only those videos are added.
        Otherwise, videos are fetched from YouTube for the given channel_url.
        """
        new_count = 0
        skipped_count = 0
        target_channel = channel_url or settings.DEFAULT_YOUTUBE_CHANNEL

        try:
            if videos is not None:
                # Sync explicitly passed videos
                total_found = len(videos)
                channel_title = target_channel
                resolved_channel_url = target_channel

                for item in videos:
                    if not channel_title and item.channel_name:
                        channel_title = item.channel_name
                    if resolved_channel_url == target_channel and item.channel_url:
                        resolved_channel_url = item.channel_url

                    existing = db.query(Video).filter(Video.id == item.id).first()
                    if existing:
                        skipped_count += 1
                        continue

                    new_video = Video(
                        id=item.id,
                        title=item.title,
                        description=item.description,
                        thumbnail_url=item.thumbnail_url,
                        duration=item.duration,
                        duration_formatted=item.duration_formatted,
                        channel_name=item.channel_name,
                        channel_id=item.channel_id,
                        channel_url=item.channel_url,
                        view_count=item.view_count,
                        published_at=item.published_at,
                        webpage_url=item.webpage_url,
                        is_downloaded=False,
                        download_status="not_downloaded",
                    )
                    db.add(new_video)
                    new_count += 1

                db.commit()

                return SyncChannelResponse(
                    status="success",
                    channel_title=channel_title,
                    channel_url=resolved_channel_url,
                    total_found=total_found,
                    new_added=new_count,
                    updated=0,
                    skipped=skipped_count,
                    message=f"Synced {new_count} new video(s) ({skipped_count} skipped - already exist in library).",
                )

            # Fallback: extract from YouTube and sync
            data = YtdlpService.extract_channel_metadata(
                target_channel, limit=limit, offset=offset
            )
            raw_videos = data.get("videos", [])
            total_found = len(raw_videos)

            for item in raw_videos:
                vid_id = item["id"]
                existing = db.query(Video).filter(Video.id == vid_id).first()

                if existing:
                    skipped_count += 1
                    continue

                new_video = Video(
                    id=vid_id,
                    title=item["title"],
                    description=item.get("description"),
                    thumbnail_url=item["thumbnail_url"],
                    duration=item["duration"],
                    duration_formatted=item["duration_formatted"],
                    channel_name=item["channel_name"],
                    channel_id=item["channel_id"],
                    channel_url=item["channel_url"],
                    view_count=item["view_count"],
                    published_at=item["published_at"],
                    webpage_url=item["webpage_url"],
                    is_downloaded=False,
                    download_status="not_downloaded",
                )
                db.add(new_video)
                new_count += 1

            db.commit()

            channel_title = data.get("channel_title", target_channel)
            resolved_channel_url = data.get("channel_url", target_channel)

            return SyncChannelResponse(
                status="success",
                channel_title=channel_title,
                channel_url=resolved_channel_url,
                total_found=total_found,
                new_added=new_count,
                updated=0,
                skipped=skipped_count,
                message=f"Synced {new_count} new video(s) ({skipped_count} skipped - already in library) from {channel_title}.",
            )

        except Exception:
            db.rollback()
            raise

    @staticmethod
    def mark_download_pending(db: Session, video: Video) -> Video:
        """Mark video download state as pending and reset progress."""
        try:
            video.download_status = "pending"
            video.download_progress = 0.0
            video.error_message = None
            db.commit()
            db.refresh(video)
            return video
        except Exception:
            db.rollback()
            raise

    @staticmethod
    def get_download_status(db: Session, video_id: str) -> VideoStatusResponse | None:
        """Fetch video download status details by video ID."""
        video = db.query(Video).filter(Video.id == video_id).first()
        if not video:
            return None

        return VideoStatusResponse(
            video_id=video.id,
            is_downloaded=video.is_downloaded,
            download_status=video.download_status,
            download_progress=video.download_progress,
            local_file_path=video.local_file_path,
            file_size_bytes=video.file_size_bytes,
            error_message=video.error_message,
        )

    @staticmethod
    def get_video(db: Session, video_id: str) -> VideoResponse | None:
        """Fetch a single video from the database by its ID, validated as VideoResponse."""
        video = db.query(Video).filter(Video.id == video_id).first()
        if not video:
            return None
        return VideoResponse.model_validate(video)

    @staticmethod
    def create_video(db: Session, request: VideoCreateRequest) -> VideoResponse:
        """Create a new video resource in the catalog."""
        vid_id = request.id
        if not vid_id:
            if request.webpage_url:
                match = re.search(
                    r"(?:v=|/videos/|youtu\.be/|/shorts/)([a-zA-Z0-9_-]{11})",
                    request.webpage_url,
                )
                if match:
                    vid_id = match.group(1)
            if not vid_id:
                vid_id = f"vid_{uuid.uuid4().hex[:12]}"

        existing = db.query(Video).filter(Video.id == vid_id).first()
        if existing:
            raise ValueError(f"Video with id '{vid_id}' already exists")

        webpage_url = request.webpage_url or f"https://www.youtube.com/watch?v={vid_id}"
        duration_formatted = request.duration_formatted or format_duration(
            request.duration
        )

        new_video = Video(
            id=vid_id,
            title=request.title,
            description=request.description,
            thumbnail_url=request.thumbnail_url,
            duration=request.duration,
            duration_formatted=duration_formatted,
            channel_name=request.channel_name,
            channel_id=request.channel_id,
            channel_url=request.channel_url,
            view_count=request.view_count,
            published_at=request.published_at,
            webpage_url=webpage_url,
            is_downloaded=False,
            download_status="not_downloaded",
            download_progress=0.0,
        )
        db.add(new_video)
        db.commit()
        db.refresh(new_video)
        return VideoResponse.model_validate(new_video)

    @staticmethod
    def update_video(
        db: Session, video_id: str, request: VideoUpdateRequest
    ) -> VideoResponse | None:
        """Update fields on an existing video resource."""
        video = db.query(Video).filter(Video.id == video_id).first()
        if not video:
            return None

        update_data = request.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(video, field, value)

        if (
            "duration" in update_data
            and "duration_formatted" not in update_data
            and video.duration is not None
        ):
            video.duration_formatted = format_duration(video.duration)

        video.updated_at = datetime.now(UTC)
        db.commit()
        db.refresh(video)
        return VideoResponse.model_validate(video)

    @staticmethod
    def delete_video(
        db: Session, video_id: str, delete_file: bool = True
    ) -> DeleteVideoResponse | None:
        """Delete video record from database, clean up associated files and render jobs."""
        video = db.query(Video).filter(Video.id == video_id).first()
        if not video:
            return None

        if (
            delete_file
            and video.local_file_path
            and os.path.exists(video.local_file_path)
        ):
            try:
                os.remove(video.local_file_path)
            except OSError as err:
                logger.warning("Error removing video file for %s: %s", video_id, err)

        # Clean up associated render jobs in DB
        db.query(RenderJob).filter(RenderJob.video_id == video_id).delete(
            synchronize_session=False
        )

        db.delete(video)
        db.commit()

        return DeleteVideoResponse(
            status="success",
            message=f"Video '{video_id}' deleted successfully",
        )

    @staticmethod
    def start_download(
        db: Session,
        video_id: str,
        quality: str | None = None,
        background_tasks: BackgroundTasks | None = None,
    ) -> DownloadTaskResponse | None:
        """
        Initiate video download. Checks catalog existence and current download state,
        marks pending in database, and dispatches task to Celery or FastAPI BackgroundTasks.
        """
        video = db.query(Video).filter(Video.id == video_id).first()
        if not video:
            return None

        if video.download_status == "downloading":
            return DownloadTaskResponse(
                video_id=video_id,
                download_status=video.download_status,
                download_progress=video.download_progress,
                local_file_path=video.local_file_path,
                message="Download is already in progress.",
            )

        if (
            video.is_downloaded
            and video.local_file_path
            and os.path.exists(video.local_file_path)
        ):
            return DownloadTaskResponse(
                video_id=video_id,
                download_status="completed",
                download_progress=100.0,
                local_file_path=video.local_file_path,
                message="Video is already downloaded locally.",
            )

        VideoService.mark_download_pending(db=db, video=video)

        task_id = None
        dispatched_to_celery = False

        if is_celery_broker_online():
            logger.info("Dispatching to Celery worker for video %s", video_id)
            try:
                async_result = download_video_celery_task.delay(video_id, quality)
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
            if background_tasks:
                background_tasks.add_task(execute_download_job, video_id, quality)
            else:
                execute_download_job(video_id, quality)
            task_id = f"bg-{video_id}"

        return DownloadTaskResponse(
            video_id=video_id,
            download_status="pending",
            download_progress=0.0,
            task_id=task_id,
            message="Download queued successfully"
            + (" via Celery" if dispatched_to_celery else " in background worker"),
        )

    @staticmethod
    def delete_downloaded_video(
        db: Session,
        video_id: str | None = None,
        video: Video | None = None,
    ) -> DeleteVideoResponse | None:
        """Remove local downloaded video file from disk and reset download state in database."""
        target_video = video
        if target_video is None and video_id is not None:
            target_video = db.query(Video).filter(Video.id == video_id).first()

        if not target_video:
            return None

        if target_video.local_file_path and os.path.exists(
            target_video.local_file_path
        ):
            os.remove(target_video.local_file_path)

        try:
            target_video.is_downloaded = False
            target_video.download_status = "not_downloaded"
            target_video.download_progress = 0.0
            target_video.local_file_path = None
            target_video.file_size_bytes = None
            db.commit()
        except Exception:
            db.rollback()
            raise

        return DeleteVideoResponse(
            status="success",
            message=f"Local file for video {target_video.id} deleted",
        )

    @staticmethod
    def execute_download_job(
        video_id: str,
        quality: str = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        celery_task_instance=None,
        db_session: Session | None = None,
    ) -> dict[str, Any]:
        """Core download execution logic using VideoService, shared by Celery and background workers."""
        is_external_session = db_session is not None
        db = db_session if db_session is not None else get_task_db_session()
        video = None
        last_reported_progress = 0.0

        try:
            video = VideoService.get_video_by_id(db, video_id)
            if not video:
                logger.error("Video ID %s not found in database", video_id)
                return {"status": "failed", "error": f"Video {video_id} not found"}

            video.download_status = "downloading"
            video.download_progress = 1.0
            video.error_message = None
            db.commit()

            def on_progress(data: dict[str, Any]):
                nonlocal last_reported_progress
                pct = data.get("progress", 0.0)
                if pct - last_reported_progress >= 5.0 or pct >= 99.0:
                    last_reported_progress = pct
                    try:
                        video.download_progress = pct
                        db.commit()
                        if celery_task_instance:
                            celery_task_instance.update_state(
                                state="PROGRESS",
                                meta={"progress": pct, "speed": data.get("speed")},
                            )
                    except Exception as commit_err:
                        logger.warning(
                            "Error committing progress update: %s", commit_err
                        )

            result = YtdlpService.download_video(
                video_id=video_id, quality=quality, progress_callback=on_progress
            )

            video.download_status = "completed"
            video.download_progress = 100.0
            video.is_downloaded = True
            video.local_file_path = result["local_file_path"]
            video.file_size_bytes = result["file_size_bytes"]
            video.error_message = None
            db.commit()

            logger.info(
                "Successfully downloaded video %s to %s",
                video_id,
                result["local_file_path"],
            )
            return {
                "status": "completed",
                "video_id": video_id,
                "file_path": result["local_file_path"],
                "file_size": result["file_size_bytes"],
            }

        except Exception as e:
            logger.exception("Failed downloading video %s", video_id)
            try:
                if video:
                    video.download_status = "failed"
                    video.error_message = str(e)
                    db.commit()
            except Exception as e2:
                logger.error("Error committing download job failure: %s", e2)
            return {"status": "failed", "video_id": video_id, "error": str(e)}
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


def execute_download_job(
    video_id: str,
    quality: str = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
    celery_task_instance=None,
    db_session: Session | None = None,
) -> dict[str, Any]:
    """Execute download job via VideoService."""
    return VideoService.execute_download_job(
        video_id=video_id,
        quality=quality,
        celery_task_instance=celery_task_instance,
        db_session=db_session,
    )


@celery_app.task(bind=True, name="download_video_task")
def download_video_celery_task(
    self,
    video_id: str,
    quality: str = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
):
    """Celery task for video download."""
    logger.info(
        "Celery task started: downloading video %s (task_id: %s)",
        video_id,
        self.request.id,
    )
    return VideoService.execute_download_job(
        video_id=video_id, quality=quality, celery_task_instance=self
    )
