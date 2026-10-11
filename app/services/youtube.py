"""YouTube service using yt-dlp for channel metadata extraction and video downloads."""

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yt_dlp

from app.config import settings

logger = logging.getLogger(__name__)


def format_duration(seconds: int | None) -> str:
    """Format duration in seconds to MM:SS or HH:MM:SS."""
    if not seconds or seconds <= 0:
        return "0:00"
    seconds = int(seconds)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def normalize_channel_url(channel_input: str) -> str:
    """Normalize channel handle or URL to the /videos tab URL."""
    clean = channel_input.strip()
    if clean.startswith("@"):
        return f"https://www.youtube.com/{clean}/videos"
    if clean.startswith("UC") and len(clean) == 24:
        return f"https://www.youtube.com/channel/{clean}/videos"
    if "youtube.com" in clean or "youtu.be" in clean:
        if not clean.endswith("/videos") and "/@" in clean:
            return f"{clean.rstrip('/')}/videos"
        return clean
    # Default to handle format
    return f"https://www.youtube.com/@{clean.lstrip('@')}/videos"


class YouTubeService:
    """Service for interacting with YouTube via yt-dlp."""

    @staticmethod
    def extract_channel_metadata(
        channel_input: str, limit: int = 20, offset: int = 0
    ) -> dict[str, Any]:
        """
        Extract video list from a channel without downloading.
        Uses flat extraction for maximum speed.
        """
        target_url = normalize_channel_url(channel_input)
        logger.info(
            "Extracting channel videos from: %s (limit: %d) (offset: %d)",
            target_url,
            limit,
            offset,
        )

        ydl_opts = {
            "extract_flat": True,
            # "playlistreverse": True,
            "playlist_items": f"{offset}-{limit}",
            # "playliststart": offset,
            # "playlistend": limit,
            "skip_download": True,
            "quiet": True,
            "no_warnings": True,
            "ignoreerrors": True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(target_url, download=False)
            if not info:
                raise ValueError(
                    f"Could not fetch metadata for channel: {channel_input}"
                )

            channel_title = (
                info.get("channel")
                or info.get("uploader")
                or info.get("title")
                or channel_input
            )
            channel_id = info.get("channel_id") or info.get("uploader_id")
            channel_url = (
                info.get("channel_url") or info.get("webpage_url") or target_url
            )

            entries = info.get("entries") or []
            videos: list[dict[str, Any]] = []

            for entry in entries:
                if not entry:
                    continue

                vid_id = entry.get("id")
                if not vid_id:
                    continue

                duration = int(entry.get("duration") or 0)
                # Pick highest quality thumbnail available
                thumbnails = entry.get("thumbnails") or []
                thumb_url = None
                if thumbnails:
                    thumb_url = thumbnails[-1].get("url")
                if not thumb_url:
                    thumb_url = f"https://i.ytimg.com/vi/{vid_id}/hqdefault.jpg"

                # Parse upload date if available (YYYYMMDD -> YYYY-MM-DD)
                raw_date = entry.get("upload_date")
                formatted_date = None
                if raw_date and len(raw_date) == 8:
                    formatted_date = f"{raw_date[0:4]}-{raw_date[4:6]}-{raw_date[6:8]}"

                video = {
                    "id": vid_id,
                    "title": entry.get("title") or f"Video {vid_id}",
                    "description": entry.get("description") or "",
                    "thumbnail_url": thumb_url,
                    "duration": duration,
                    "duration_formatted": format_duration(duration),
                    "channel_name": entry.get("uploader")
                    or entry.get("channel")
                    or channel_title,
                    "channel_id": entry.get("channel_id") or channel_id,
                    "channel_url": channel_url,
                    "view_count": int(entry.get("view_count") or 0),
                    "published_at": formatted_date,
                    "webpage_url": entry.get("url")
                    or f"https://www.youtube.com/watch?v={vid_id}",
                }
                videos.append(video)

            return {
                "channel_title": channel_title,
                "channel_id": channel_id,
                "channel_url": target_url,
                "videos": videos,
            }

    @staticmethod
    def download_video(
        video_id: str,
        quality: str = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        """
        Download a specific video using yt-dlp to local storage.
        Merges to MP4 with standard codecs suitable for our rendering engine.
        """
        output_template = str(settings.downloads_path / f"{video_id}.%(ext)s")
        expected_final_file = settings.downloads_path / f"{video_id}.mp4"

        def ydl_progress_hook(d: dict[str, Any]):
            status = d.get("status")
            if status == "downloading":
                total_bytes = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                downloaded_bytes = d.get("downloaded_bytes") or 0
                pct = 0.0
                if total_bytes > 0:
                    pct = round((downloaded_bytes / total_bytes) * 100, 1)

                if progress_callback:
                    progress_callback(
                        {
                            "status": "downloading",
                            "progress": pct,
                            "downloaded_bytes": downloaded_bytes,
                            "total_bytes": total_bytes,
                            "speed": d.get("speed"),
                            "eta": d.get("eta"),
                        }
                    )
            elif status == "finished":
                if progress_callback:
                    progress_callback(
                        {
                            "status": "processing",
                            "progress": 99.0,
                        }
                    )

        ydl_opts = {
            "format": quality,
            "outtmpl": output_template,
            "merge_output_format": "mp4",
            "progress_hooks": [ydl_progress_hook],
            "quiet": True,
            "no_warnings": True,
            "overwrites": True,
            "postprocessors": [
                {
                    "key": "FFmpegVideoRemuxer",
                    "preferedformat": "mp4",
                }
            ],
        }

        target_url = f"https://www.youtube.com/watch?v={video_id}"
        logger.info(
            "Starting download for video %s to %s", video_id, expected_final_file
        )

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([target_url])

        # Locate final saved file
        final_path: Path | None = None
        if expected_final_file.exists():
            final_path = expected_final_file
        else:
            # Check for any file matching video_id in downloads dir
            matches = list(settings.downloads_path.glob(f"{video_id}.*"))
            if matches:
                final_path = matches[0]

        if not final_path or not final_path.exists():
            raise FileNotFoundError(
                f"Download completed but output file not found for video: {video_id}"
            )

        file_size = final_path.stat().st_size
        return {
            "status": "completed",
            "local_file_path": str(final_path),
            "file_size_bytes": file_size,
        }
