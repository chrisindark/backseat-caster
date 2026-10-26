"""Centralized, dynamic metadata generation for YouTube uploads.

All title/description/tags defaults for staged & published uploads should flow
through :func:`generate_upload_metadata` so behaviour stays consistent across
the staging resolver (RenderService.update_upload_selection), the upload engine
(YouTubeUploaderService.upload_clip_to_youtube) and any future callers.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

_BASE_TAGS = ["Gaming", "Highlights", "Gameplay"]


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def build_title(video: Any, job: Any, clip_id: str) -> str:
    """Build a dynamic, human-readable title from source + timing data."""
    start_s = _as_int(getattr(job, "start_seconds", 0.0) if job else 0.0, 0)
    dur_raw = getattr(job, "duration_seconds", None) if job else None
    dur_s = _as_int(dur_raw, 15) if dur_raw is not None else 15
    end_s = start_s + dur_s

    parent_title = _clean(getattr(video, "title", None) if video else None)
    if parent_title:
        base = f"{parent_title[:55]} - Highlight ({start_s}s-{end_s}s)".strip()
    else:
        base = f"Gameplay Highlight - {clip_id}"
    return base[:95]


def build_description(video: Any, job: Any, clip_id: str, is_short: bool) -> str:
    """Build a description referencing source video/channel and clip timing."""
    lines: list[str] = [
        "Gameplay highlight rendered with BackseatCaster AI Clip Engine.",
    ]
    video_title = _clean(getattr(video, "title", None) if video else None)
    channel_name = _clean(getattr(video, "channel_name", None) if video else None)
    webpage_url = _clean(getattr(video, "webpage_url", None) if video else None)
    start_s = _as_int(getattr(job, "start_seconds", 0.0) if job else 0.0, 0)

    if video_title:
        lines.append(f"Source: {video_title}")
    if channel_name:
        lines.append(f"Clipped from {channel_name}'s stream.")
    if webpage_url:
        sep = "&" if "?" in webpage_url else "?"
        lines.append(f"Watch the full VOD: {webpage_url}{sep}t={start_s}s")
    if getattr(job, "narration_path", None) if job else None:
        lines.append("Includes AI-generated commentary.")
    if is_short:
        lines.append("")
        lines.append("#Shorts")

    tags_line = " ".join(
        f"#{t}" for t in build_tags(video, job, is_short) if t and not t.startswith("#")
    )
    lines.append(tags_line)
    return "\n".join(lines).strip()


def build_tags(video: Any, job: Any, is_short: bool) -> list[str]:
    """Build a dynamic tag list, de-duplicating while preserving order."""
    tags: list[str] = list(_BASE_TAGS)
    channel_name = _clean(getattr(video, "channel_name", None) if video else None)
    if channel_name:
        # channel handle without leading '@', plus a readable variant
        handle = channel_name.lstrip("@").strip()
        if handle and handle not in tags:
            tags.append(handle)
    if is_short and "Shorts" not in tags:
        tags.append("Shorts")
    # De-dup, strip, keep within YouTube's 30-tag / 500-char budget
    seen: set[str] = set()
    result: list[str] = []
    for t in tags:
        t = t.strip()
        if t and t not in seen:
            seen.add(t)
            result.append(t)
    return result[:30]


def generate_upload_metadata(
    video: Any = None,
    job: Any = None,
    clip_id: str = "",
    preferred_format: str | None = None,
    existing: dict[str, Any] | None = None,
    is_short_hint: bool | None = None,
) -> dict[str, Any]:
    """Return a fully-populated upload metadata dict.

    ``existing`` values take precedence for fields that are already populated;
    only missing/empty fields are regenerated. ``preferred_format`` overrides
    the job's selected format when determining Shorts-ness.
    """
    existing = existing or {}

    fmt = (
        preferred_format
        or (getattr(job, "selected_format", None) if job else None)
        or existing.get("preferred_format")
        or "vertical_blur"
    )
    is_vertical = fmt != "landscape"
    duration = getattr(job, "duration_seconds", None) if job else None
    try:
        dur_val = float(duration) if duration is not None else 15.0
    except (TypeError, ValueError):
        dur_val = 15.0
    is_short = (
        is_short_hint
        if is_short_hint is not None
        else (is_vertical and dur_val <= 60.0)
    )

    title = _clean(existing.get("title"))
    if title is None:
        title = build_title(video, job, clip_id)

    description = _clean(existing.get("description"))
    if description is None:
        description = build_description(video, job, clip_id, bool(is_short))

    tags = existing.get("tags")
    if not isinstance(tags, list) or not tags:
        tags = build_tags(video, job, bool(is_short))
    else:
        tags = [str(t).strip() for t in tags if str(t).strip()]

    privacy = _clean(existing.get("privacy")) or "public"

    return {
        "is_selected": bool(existing.get("is_selected", False)),
        "preferred_format": fmt,
        "title": title,
        "description": description,
        "tags": tags,
        "privacy": privacy,
        "updated_at": datetime.now(UTC).isoformat(),
    }


# Backwards-compatible alias for callers expecting the older helper name.
generate_default_metadata = generate_upload_metadata
