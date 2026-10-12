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
    VideoBase,
    VideoListResponse,
    VideoResponse,
    VideoStatusResponse,
    YouTubeChannelVideoItem,
    YouTubeChannelVideosResponse,
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
        data = YouTubeService.extract_channel_metadata(
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
            data = YouTubeService.extract_channel_metadata(
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
