"""Video service containing database and business logic for video management."""

import logging
import math
import os

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import settings
from app.models.video import Video
from app.schemas.video import (
    DeleteVideoResponse,
    SyncChannelResponse,
    VideoListResponse,
    VideoResponse,
    VideoStatusResponse,
)
from app.services.youtube import YouTubeService

logger = logging.getLogger(__name__)


class VideoService:
    """Service handling database queries and business logic for videos."""

    @staticmethod
    def get_video_by_id(db: Session, video_id: str) -> Video | None:
        """Fetch a single video from the database by its ID."""
        return db.query(Video).filter(Video.id == video_id).first()

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
            if status == "downloaded":
                query = query.filter(Video.is_downloaded == True)
            elif status == "not_downloaded":
                query = query.filter(Video.is_downloaded == False)
            elif status in ["downloading", "pending"]:
                query = query.filter(
                    Video.download_status.in_(["downloading", "pending"])
                )

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
    def sync_channel(
        db: Session,
        channel_url: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> SyncChannelResponse:
        """
        Fetch latest videos from a YouTube channel via yt-dlp
        and upsert them into the database.
        """
        target_channel = channel_url or settings.DEFAULT_YOUTUBE_CHANNEL
        data = YouTubeService.extract_channel_metadata(
            target_channel, limit=limit, offset=offset
        )

        new_count = 0
        updated_count = 0

        try:
            for item in data.get("videos", []):
                vid_id = item["id"]
                existing = db.query(Video).filter(Video.id == vid_id).first()

                if existing:
                    # Update metadata while preserving local file states
                    existing.title = item["title"]
                    existing.description = item.get("description", existing.description)
                    existing.thumbnail_url = item["thumbnail_url"]
                    existing.duration = item["duration"]
                    existing.duration_formatted = item["duration_formatted"]
                    existing.channel_name = item["channel_name"]
                    existing.channel_id = item["channel_id"]
                    existing.channel_url = item["channel_url"]
                    existing.view_count = item["view_count"]
                    existing.published_at = item["published_at"]
                    existing.webpage_url = item["webpage_url"]
                    updated_count += 1
                else:
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
        except Exception:
            db.rollback()
            raise

        channel_title = data.get("channel_title", target_channel)
        resolved_channel_url = data.get("channel_url", target_channel)

        return SyncChannelResponse(
            status="success",
            channel_title=channel_title,
            channel_url=resolved_channel_url,
            total_found=len(data.get("videos", [])),
            new_added=new_count,
            updated=updated_count,
            message=f"Synced {new_count} new and updated {updated_count} videos from {channel_title}.",
        )

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
    def delete_downloaded_video(db: Session, video: Video) -> DeleteVideoResponse:
        """Remove local downloaded video file from disk and reset download state in database."""
        if video.local_file_path and os.path.exists(video.local_file_path):
            os.remove(video.local_file_path)

        try:
            video.is_downloaded = False
            video.download_status = "not_downloaded"
            video.download_progress = 0.0
            video.local_file_path = None
            video.file_size_bytes = None
            db.commit()
        except Exception:
            db.rollback()
            raise

        return DeleteVideoResponse(
            status="success",
            message=f"Local file for video {video.id} deleted",
        )
