"""Video service containing database and business logic for video management."""

import json
import logging
import math
import mimetypes
import os
import re
import shutil
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, HTTPException, UploadFile
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_task_db_session
from app.models.highlight_candidate import HighlightCandidate
from app.models.render_job import RenderJob
from app.models.video import Video
from app.rendering.probe import probe_media
from app.schemas.video import (
    DeleteVideoResponse,
    DownloadTaskResponse,
    SyncChannelResponse,
    UploadedHighlightSummary,
    VideoBase,
    VideoCreateRequest,
    VideoListResponse,
    VideoResponse,
    VideoStatusResponse,
    VideoStorageCleanupResponse,
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
                if not matches:
                    matches = [
                        m
                        for m in settings.downloads_path.glob(f"{video_id}_*.*")
                        if not m.name.endswith("_thumb.jpg")
                    ]
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
    def enrich_video_response(
        db: Session,
        video: Video,
        cand_count: int | None = None,
        render_count: int | None = None,
        uploaded_jobs: list[RenderJob] | None = None,
    ) -> VideoResponse:
        """Enrich a Video with highlight mining and YouTube upload status metrics."""
        base_resp = VideoResponse.model_validate(video)

        # 1. Candidate count
        if cand_count is None:
            cand_count = (
                db.query(HighlightCandidate)
                .filter(HighlightCandidate.video_id == video.id)
                .count()
            )
        base_resp.highlight_candidate_count = cand_count

        # 2. Render jobs count
        if render_count is None:
            render_count = (
                db.query(RenderJob).filter(RenderJob.video_id == video.id).count()
            )
        base_resp.rendered_clip_count = render_count

        # 3. Uploaded render jobs & summaries
        if uploaded_jobs is None:
            uploaded_jobs = (
                db.query(RenderJob)
                .filter(
                    RenderJob.video_id == video.id,
                    or_(
                        RenderJob.youtube_upload_status == "completed",
                        RenderJob.youtube_upload_url.isnot(None),
                    ),
                )
                .all()
            )

        base_resp.uploaded_clip_count = len(uploaded_jobs)
        base_resp.has_uploaded_highlights = len(uploaded_jobs) > 0

        uploaded_summaries: list[UploadedHighlightSummary] = []
        has_renders_on_disk = False
        renders_root = settings.renders_path

        for job in uploaded_jobs:
            title = None
            if job.upload_metadata:
                try:
                    meta = json.loads(job.upload_metadata)
                    title = meta.get("title")
                except Exception:
                    pass
            uploaded_summaries.append(
                UploadedHighlightSummary(
                    clip_id=job.clip_id,
                    youtube_video_id=job.youtube_video_id,
                    youtube_upload_url=job.youtube_upload_url,
                    youtube_uploaded_at=job.youtube_uploaded_at,
                    title=title,
                    format=job.selected_format,
                )
            )
            if not has_renders_on_disk and (renders_root / job.clip_id).exists():
                has_renders_on_disk = True

        base_resp.uploaded_highlights = uploaded_summaries
        base_resp.can_cleanup_vod = bool(
            video.is_downloaded
            and (base_resp.has_uploaded_highlights or cand_count > 0)
        )
        base_resp.can_cleanup_renders = has_renders_on_disk

        return base_resp

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
                    ),
                    or_(
                        Video.download_status.is_(None),
                        Video.download_status.notin_(["downloading", "pending"]),
                    ),
                )
            elif status == "not_downloaded":
                query = query.filter(
                    or_(
                        Video.is_downloaded.is_(False),
                        Video.is_downloaded.is_(None),
                    ),
                    or_(
                        Video.download_status.is_(None),
                        Video.download_status.notin_(
                            ["completed", "downloading", "pending"]
                        ),
                    ),
                )
            elif status in ["downloading", "pending"]:
                query = query.filter(
                    Video.download_status.in_(["downloading", "pending"])
                )
            elif status == "failed":
                query = query.filter(Video.download_status == "failed")
            elif status in ["highlights_mined", "highlights_processed"]:
                cand_subquery = db.query(HighlightCandidate.video_id).distinct()
                query = query.filter(
                    or_(
                        Video.highlight_status == "completed",
                        Video.id.in_(cand_subquery),
                    )
                )
            elif status in ["uploaded", "has_uploaded_highlights"]:
                uploaded_subquery = (
                    db.query(RenderJob.video_id)
                    .filter(
                        or_(
                            RenderJob.youtube_upload_status == "completed",
                            RenderJob.youtube_upload_url.isnot(None),
                        )
                    )
                    .distinct()
                )
                query = query.filter(Video.id.in_(uploaded_subquery))
            elif status in ["cleanup_ready", "can_cleanup"]:
                uploaded_subquery = (
                    db.query(RenderJob.video_id)
                    .filter(
                        or_(
                            RenderJob.youtube_upload_status == "completed",
                            RenderJob.youtube_upload_url.isnot(None),
                        )
                    )
                    .distinct()
                )
                query = query.filter(
                    Video.is_downloaded.is_(True),
                    Video.id.in_(uploaded_subquery),
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

        for item in items:
            if item.download_status == "completed" and not item.is_downloaded:
                item.is_downloaded = True

        first_item = items[0] if items else None
        channel_title = first_item.channel_name if first_item else None
        channel_url = first_item.channel_url if first_item else None

        # Collect video ids for bulk stats enrichment
        video_ids = [item.id for item in items]
        cand_counts_map: dict[str, int] = {}
        render_counts_map: dict[str, int] = {}
        uploaded_jobs_map: dict[str, list[RenderJob]] = {}

        if video_ids:
            for vid_id, count in (
                db.query(HighlightCandidate.video_id, func.count(HighlightCandidate.id))
                .filter(HighlightCandidate.video_id.in_(video_ids))
                .group_by(HighlightCandidate.video_id)
                .all()
            ):
                cand_counts_map[vid_id] = count

            for vid_id, count in (
                db.query(RenderJob.video_id, func.count(RenderJob.id))
                .filter(RenderJob.video_id.in_(video_ids))
                .group_by(RenderJob.video_id)
                .all()
            ):
                render_counts_map[vid_id] = count

            for job in (
                db.query(RenderJob)
                .filter(
                    RenderJob.video_id.in_(video_ids),
                    or_(
                        RenderJob.youtube_upload_status == "completed",
                        RenderJob.youtube_upload_url.isnot(None),
                    ),
                )
                .all()
            ):
                uploaded_jobs_map.setdefault(job.video_id, []).append(job)

        enriched_items = [
            VideoService.enrich_video_response(
                db=db,
                video=item,
                cand_count=cand_counts_map.get(item.id, 0),
                render_count=render_counts_map.get(item.id, 0),
                uploaded_jobs=uploaded_jobs_map.get(item.id, []),
            )
            for item in items
        ]

        return VideoListResponse(
            items=enriched_items,
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
        return VideoService.enrich_video_response(db=db, video=video)

    @staticmethod
    def cleanup_video_storage(
        db: Session,
        video_id: str,
        clean_vod: bool = True,
        clean_uploaded_renders: bool = True,
        clean_all_renders: bool = False,
    ) -> VideoStorageCleanupResponse:
        """Clean up local video VOD files and/or render folders from disk to reclaim storage."""
        video = db.query(Video).filter(Video.id == video_id).first()
        if not video:
            raise HTTPException(status_code=404, detail=f"Video '{video_id}' not found")

        reclaimed_bytes = 0
        vod_deleted = False
        renders_deleted_count = 0
        renders_root = settings.renders_path

        # 1. Clean downloaded source VOD if requested
        if clean_vod:
            if video.local_file_path and os.path.exists(video.local_file_path):
                try:
                    file_size = os.path.getsize(video.local_file_path)
                    os.remove(video.local_file_path)
                    reclaimed_bytes += file_size
                    vod_deleted = True
                except OSError as e:
                    logger.warning("Error deleting VOD file for %s: %s", video_id, e)

            # Also check expected download path if local_file_path was missing/stale
            default_path = settings.downloads_path / f"{video_id}.mp4"
            if not vod_deleted and default_path.exists():
                try:
                    file_size = default_path.stat().st_size
                    default_path.unlink()
                    reclaimed_bytes += file_size
                    vod_deleted = True
                except OSError:
                    pass

            # Remove thumb if present
            thumb_path = settings.downloads_path / f"{video_id}_thumb.jpg"
            if thumb_path.exists():
                try:
                    reclaimed_bytes += thumb_path.stat().st_size
                    thumb_path.unlink()
                except OSError:
                    pass

            video.is_downloaded = False
            video.download_status = "not_downloaded"
            video.download_progress = 0.0
            video.local_file_path = None
            video.file_size_bytes = None

        # 2. Clean render directories if requested
        if clean_all_renders or clean_uploaded_renders:
            render_jobs = (
                db.query(RenderJob).filter(RenderJob.video_id == video_id).all()
            )
            for job in render_jobs:
                is_uploaded = (
                    job.youtube_upload_status == "completed"
                    or job.youtube_upload_url is not None
                )
                if clean_all_renders or (clean_uploaded_renders and is_uploaded):
                    clip_dir = renders_root / job.clip_id
                    if clip_dir.exists() and clip_dir.is_dir():
                        dir_size = sum(
                            f.stat().st_size for f in clip_dir.rglob("*") if f.is_file()
                        )
                        shutil.rmtree(clip_dir, ignore_errors=True)
                        reclaimed_bytes += dir_size
                        renders_deleted_count += 1
                    elif job.output_dir and Path(job.output_dir).exists():
                        p = Path(job.output_dir)
                        if p.is_dir():
                            dir_size = sum(
                                f.stat().st_size for f in p.rglob("*") if f.is_file()
                            )
                            shutil.rmtree(p, ignore_errors=True)
                            reclaimed_bytes += dir_size
                            renders_deleted_count += 1

        db.commit()

        # Format reclaimed size
        mb = reclaimed_bytes / (1024 * 1024)
        if mb >= 1024:
            reclaimed_formatted = f"{(mb / 1024):.2f} GB"
        else:
            reclaimed_formatted = f"{mb:.1f} MB"

        messages = []
        if vod_deleted:
            messages.append("Source VOD removed from disk")
        if renders_deleted_count > 0:
            messages.append(f"{renders_deleted_count} render folder(s) cleaned")
        if not messages:
            messages.append("No local files needed removal")

        return VideoStorageCleanupResponse(
            video_id=video_id,
            reclaimed_bytes=reclaimed_bytes,
            reclaimed_formatted=reclaimed_formatted,
            vod_deleted=vod_deleted,
            renders_deleted_count=renders_deleted_count,
            message="; ".join(messages),
        )

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
    def catalog_local_file(
        db: Session,
        *,
        video_id: str,
        dest_path: Path,
        original_filename: str,
        title: str | None = None,
        channel_name: str | None = None,
        channel_id: str = "local_obs",
        channel_url: str = "local://obs",
    ) -> VideoResponse:
        """Probe a local file already on disk and register it as a catalogued video.

        Shared by the OBS drag-and-drop upload and the zero-click watch folder so
        both ingests produce identical catalog rows, thumbnails and metadata.
        """
        probe = probe_media(dest_path)
        duration_s = max(1, int(round(probe.duration)))
        duration_str = format_duration(duration_s)
        file_size = dest_path.stat().st_size

        # Generate a video frame thumbnail at 1s (or midpoint if duration < 1s)
        thumb_path = settings.downloads_path / f"{video_id}_thumb.jpg"
        seek_sec = min(1.0, max(0.0, probe.duration / 2.0))
        thumbnail_url = None
        try:
            thumb_proc = subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-ss",
                    f"{seek_sec:.2f}",
                    "-i",
                    str(dest_path),
                    "-vframes",
                    "1",
                    "-q:v",
                    "2",
                    str(thumb_path),
                ],
                capture_output=True,
                check=False,
                timeout=15,
            )
            if thumb_path.exists() and thumb_path.stat().st_size > 0:
                thumbnail_url = f"{settings.API_PREFIX}/videos/{video_id}/thumbnail"
            else:
                logger.warning(
                    "Thumbnail generation produced empty file: %s", thumb_proc.stderr
                )
        except Exception as thumb_err:
            logger.warning(
                "Could not generate thumbnail for %s: %s", video_id, thumb_err
            )

        clean_title = (
            title.strip()
            if title and title.strip()
            else Path(original_filename).stem.replace("_", " ").title()
        )

        new_video = Video(
            id=video_id,
            title=clean_title,
            description=f"Local OBS recording imported from {original_filename} ({probe.width}x{probe.height}, {probe.fps} FPS)",
            thumbnail_url=thumbnail_url,
            duration=duration_s,
            duration_formatted=duration_str,
            channel_name=channel_name or "OBS Studio",
            channel_id=channel_id,
            channel_url=channel_url,
            view_count=0,
            published_at=datetime.now(UTC).strftime("%Y-%m-%d"),
            webpage_url=f"file://{dest_path}",
            is_downloaded=True,
            local_file_path=str(dest_path),
            file_size_bytes=file_size,
            download_status="completed",
            download_progress=100.0,
            error_message=None,
        )
        db.add(new_video)
        db.commit()
        db.refresh(new_video)
        return VideoResponse.model_validate(new_video)

    @staticmethod
    def upload_local_video(
        db: Session,
        file: UploadFile,
        title: str | None = None,
        channel_name: str | None = None,
        background_tasks: BackgroundTasks | None = None,
    ) -> VideoResponse:
        """
        Handle direct local video upload (OBS drag-and-drop or local file import).
        Saves file to downloads directory, probes metadata, extracts video thumbnail,
        and catalogues the video as immediately downloaded and ready for clipping.
        """
        original_filename = file.filename or "recording.mp4"
        suffix = Path(original_filename).suffix.lower()
        allowed_extensions = {".mp4", ".mkv", ".mov", ".webm", ".flv", ".ts", ".m4v"}
        if suffix not in allowed_extensions:
            raise ValueError(
                f"Unsupported video file format '{suffix}'. Supported formats: {', '.join(sorted(allowed_extensions))}"
            )

        video_id = f"obs_{uuid.uuid4().hex[:10]}"
        safe_stem = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", Path(original_filename).stem)
        saved_filename = f"{video_id}_{safe_stem}{suffix}"
        dest_path = settings.downloads_path / saved_filename

        settings.downloads_path.mkdir(parents=True, exist_ok=True)

        try:
            with open(dest_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
        except Exception as write_err:
            if dest_path.exists():
                try:
                    dest_path.unlink()
                except OSError:
                    pass
            raise RuntimeError(f"Failed writing uploaded video to disk: {write_err}")

        video_res = VideoService.catalog_local_file(
            db=db,
            video_id=video_id,
            dest_path=dest_path,
            original_filename=original_filename,
            title=title,
            channel_name=channel_name,
        )

        # Tier 2: chain straight into highlight mining when enabled.
        from app.services.auto_mine import AutoMineService

        AutoMineService.trigger_after_ingest(
            db, video_res.id, background_tasks=background_tasks
        )
        return video_res

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

        # Remove local thumbnail file if present
        thumb_path = settings.downloads_path / f"{video_id}_thumb.jpg"
        if thumb_path.exists():
            try:
                os.remove(thumb_path)
            except OSError:
                pass

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

        # Remove local thumbnail file if present
        thumb_path = settings.downloads_path / f"{target_video.id}_thumb.jpg"
        if thumb_path.exists():
            try:
                os.remove(thumb_path)
            except OSError:
                pass

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
        quality: str
        | None = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
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

            # Tier 2: chain straight into highlight mining when enabled.
            try:
                from app.services.auto_mine import AutoMineService

                mine_result = AutoMineService.trigger_after_ingest(db, video_id)
                logger.info("Auto-mine after download %s: %s", video_id, mine_result)
            except Exception as mine_err:  # never fail a finished download
                logger.warning(
                    "Auto-mine dispatch failed for video %s: %s", video_id, mine_err
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
    quality: str | None = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
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
