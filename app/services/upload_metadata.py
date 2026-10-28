"""Centralized, dynamic metadata generation for YouTube uploads.

All title/description/tags defaults for staged & published uploads flow
through :func:`generate_upload_metadata` so behaviour stays consistent across
the staging resolver (RenderService.update_upload_selection), the upload engine
(YouTubeUploaderService.upload_clip_to_youtube), highlight auto-staging,
and metadata regeneration callers.
"""

from __future__ import annotations

import json
import logging
import re
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


def _extract_job_meta(job: Any) -> dict[str, Any]:
    if not job:
        return {}
    raw = getattr(job, "upload_metadata", None)
    if raw and isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
    return {}


def _extract_candidate_details(candidate: Any) -> dict[str, Any]:
    if candidate is None:
        return {}
    if isinstance(candidate, dict):
        details = candidate.get("details")
        if isinstance(details, dict):
            return details
        return candidate
    raw = getattr(candidate, "details_json", None)
    if raw and isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
    details = getattr(candidate, "details", None)
    if isinstance(details, dict):
        return details
    return {}


def _extract_candidate_tags(candidate: Any) -> list[str]:
    if candidate is None:
        return []
    tags = getattr(candidate, "suggested_tags", None)
    if isinstance(tags, list):
        return [str(t).strip() for t in tags if str(t).strip()]
    if isinstance(candidate, dict):
        raw_tags = candidate.get("suggested_tags")
        if isinstance(raw_tags, list):
            return [str(t).strip() for t in raw_tags if str(t).strip()]
    raw_json = getattr(candidate, "suggested_tags_json", None)
    if not raw_json and isinstance(candidate, dict):
        raw_json = candidate.get("suggested_tags_json")
    if raw_json and isinstance(raw_json, str):
        try:
            parsed = json.loads(raw_json)
            if isinstance(parsed, list):
                return [str(t).strip() for t in parsed if str(t).strip()]
        except Exception:
            pass
    return []


def _truncate_title(title: str, max_len: int = 95) -> str:
    clean = re.sub(r"\s+", " ", title).strip("\"' ")
    if len(clean) <= max_len:
        return clean
    truncated = clean[:max_len].rsplit(" ", 1)[0].rstrip()
    return truncated if truncated else clean[:max_len]


def build_title(
    video: Any = None,
    job: Any = None,
    clip_id: str = "",
    candidate: Any = None,
    hero_name: str | None = None,
    clip_context: str | None = None,
    game: str | None = None,
    is_short: bool = True,
) -> str:
    """Build a dynamic, human-readable title incorporating hero, context, and candidate facts."""
    job_meta = _extract_job_meta(job)
    cand_details = _extract_candidate_details(candidate)

    hero = (
        _clean(hero_name)
        or _clean(job_meta.get("hero_name"))
        or _clean(cand_details.get("hero_name"))
        or _clean(cand_details.get("character_name"))
    )
    context = _clean(clip_context) or _clean(job_meta.get("clip_context"))
    game_name = (
        _clean(game)
        or _clean(job_meta.get("game"))
        or _clean(getattr(candidate, "game", None) if candidate else None)
        or _clean(getattr(video, "game", None) if video else None)
    )
    if not game_name and video:
        vtitle = str(getattr(video, "title", "")).lower()
        if "marvel rivals" in vtitle:
            game_name = "Marvel Rivals"
        elif any(k in vtitle for k in ("fall guys", "fall_guys", "fallguys")):
            game_name = "Fall Guys"

    game_tag = f"#{game_name.replace(' ', '')}" if game_name else ""

    # Check for pre-existing suggested_title from highlight candidate
    sugg_title = _clean(
        getattr(candidate, "suggested_title", None) if candidate else None
    )
    if not sugg_title and isinstance(candidate, dict):
        sugg_title = _clean(candidate.get("suggested_title"))

    if sugg_title:
        title = sugg_title
        # If hero is specified and not already in suggested title, integrate it
        if hero and hero.lower() not in title.lower():
            adjectives = [
                "Insane",
                "Unreal",
                "Crazy",
                "Clean",
                "Huge",
                "Unstoppable",
                "Clutch",
            ]
            matched_adj = None
            for adj in adjectives:
                if title.startswith(adj + " "):
                    matched_adj = adj
                    break
            if matched_adj:
                remainder = title[len(matched_adj) + 1 :]
                title = f"{matched_adj} {hero} {remainder}"
            else:
                title = f"{hero}: {title}"

        # Add game hashtag if space permits and not already included
        if game_tag and game_tag.lower() not in title.lower():
            if len(title) + len(game_tag) + 1 <= 95:
                title = f"{title} {game_tag}"

        return _truncate_title(title)

    # If no suggested_title, build deterministically from event / hero / context
    event_type = _clean(getattr(candidate, "event_type", None) if candidate else None)
    if not event_type and isinstance(candidate, dict):
        event_type = _clean(candidate.get("event_type"))
    if not event_type and cand_details:
        event_type = _clean(cand_details.get("event_type"))

    is_team_wipe = bool(cand_details.get("is_team_wipe") or event_type == "team_wipe")
    is_ot = str(cand_details.get("game_phase", "")).lower() == "overtime"
    streak_count = cand_details.get("streak_count") or cand_details.get("kill_count")
    hero_prefix = f"{hero} " if hero else ""
    tag_suffix = f" {game_tag}" if game_tag else ""

    if is_team_wipe:
        title = (
            f"Insane {hero_prefix}Team Wipe in Overtime! 💥{tag_suffix}"
            if is_ot
            else f"Insane {hero_prefix}Team Wipe Ultimate! 💥{tag_suffix}"
        )
    elif event_type == "penta_ko" or streak_count == 5:
        title = (
            f"Unreal {hero_prefix}5-Player KO Streak in Overtime! 🔥{tag_suffix}"
            if is_ot
            else f"Unreal {hero_prefix}5-Player KO Streak! 🔥{tag_suffix}"
        )
    elif event_type == "quad_ko" or streak_count == 4:
        title = (
            f"Crazy {hero_prefix}Quad KO in Overtime! ⚡{tag_suffix}"
            if is_ot
            else f"Crazy {hero_prefix}Quad KO Chain! ⚡{tag_suffix}"
        )
    elif event_type == "triple_ko" or streak_count == 3:
        title = (
            f"Clean {hero_prefix}Triple KO in Overtime! 🔥{tag_suffix}"
            if is_ot
            else f"Clean {hero_prefix}Triple KO Highlight! 🔥{tag_suffix}"
        )
    elif event_type == "shutdown":
        title = f"Huge {hero_prefix}Ultimate Shutdown Denied! 🛑{tag_suffix}"
    elif event_type == "objective_clutch" or is_ot:
        title = f"Clutch {hero_prefix}Overtime Defense! ⚡{tag_suffix}"
    elif event_type == "crown_victory":
        title = f"Unreal Fall Guys Crown Victory! 👑{tag_suffix}"
    elif event_type == "round_qualified":
        title = f"Insane Fall Guys Round Qualification! ⚡{tag_suffix}"
    elif event_type == "final_round":
        title = f"Fall Guys Final Round Intensity! 🔥{tag_suffix}"
    elif event_type == "eliminated":
        title = f"Heartbreaking Fall Guys Elimination! 💀{tag_suffix}"
    elif event_type == "round_over":
        title = f"Fall Guys Round Over Chaos! 🏃{tag_suffix}"
    elif hero and context:
        title = f"{hero}: {context} 🔥{tag_suffix}"
    elif hero:
        title = f"Unstoppable {hero} Gameplay Highlight! 🔥{tag_suffix}"
    elif context:
        title = f"{context} - Gameplay Highlight 🔥{tag_suffix}"
    else:
        # Parent video timing fallback
        parent_title = _clean(getattr(video, "title", None) if video else None)
        start_s = _as_int(getattr(job, "start_seconds", 0.0) if job else 0.0, 0)
        dur_raw = getattr(job, "duration_seconds", None) if job else None
        dur_s = _as_int(dur_raw, 15) if dur_raw is not None else 15
        end_s = start_s + dur_s
        if parent_title:
            title = f"{parent_title[:55]} - Highlight ({start_s}s-{end_s}s){tag_suffix}"
        else:
            title = f"Gameplay Highlight - {clip_id}{tag_suffix}"

    return _truncate_title(title)


def build_tags(
    video: Any = None,
    job: Any = None,
    is_short: bool = True,
    candidate: Any = None,
    hero_name: str | None = None,
    game: str | None = None,
) -> list[str]:
    """Build a dynamic tag list incorporating hero, game, candidate tags and event types."""
    job_meta = _extract_job_meta(job)
    cand_details = _extract_candidate_details(candidate)

    hero = (
        _clean(hero_name)
        or _clean(job_meta.get("hero_name"))
        or _clean(cand_details.get("hero_name"))
        or _clean(cand_details.get("character_name"))
    )
    game_name = (
        _clean(game)
        or _clean(job_meta.get("game"))
        or _clean(getattr(candidate, "game", None) if candidate else None)
        or _clean(getattr(video, "game", None) if video else None)
    )
    if not game_name and video:
        vtitle = str(getattr(video, "title", "")).lower()
        if "marvel rivals" in vtitle:
            game_name = "Marvel Rivals"
        elif any(k in vtitle for k in ("fall guys", "fall_guys", "fallguys")):
            game_name = "Fall Guys"

    tags: list[str] = []

    # 1. Candidate's own tags (from mining/detection)
    cand_tags = _extract_candidate_tags(candidate)
    for ct in cand_tags:
        ct_clean = ct.lstrip("#").strip()
        if ct_clean and ct_clean not in tags:
            tags.append(ct_clean)

    # 2. Hero tags
    if hero:
        if hero not in tags:
            tags.append(hero)
        if game_name:
            combo = f"{game_name} {hero}"
            if combo not in tags:
                tags.append(combo)
        gameplay_tag = f"{hero} Gameplay"
        if gameplay_tag not in tags:
            tags.append(gameplay_tag)

    # 3. Game tags
    if game_name:
        if game_name not in tags:
            tags.append(game_name)
        compact = game_name.replace(" ", "")
        if compact and compact not in tags:
            tags.append(compact)

    # 4. Event-specific tags
    event_type = _clean(getattr(candidate, "event_type", None) if candidate else None)
    if not event_type and cand_details:
        event_type = _clean(cand_details.get("event_type"))
    if event_type:
        ev_norm = event_type.replace("_", " ")
        if ev_norm not in tags:
            tags.append(ev_norm)
        if event_type == "team_wipe":
            if "team wipe" not in tags:
                tags.append("team wipe")
            if "teamwipe" not in tags:
                tags.append("teamwipe")
        elif event_type in ("penta_ko", "kill_streak"):
            if "penta kill" not in tags:
                tags.append("penta kill")
            if "kill streak" not in tags:
                tags.append("kill streak")
        elif event_type == "quad_ko":
            if "quad kill" not in tags:
                tags.append("quad kill")
        elif event_type == "triple_ko":
            if "triple kill" not in tags:
                tags.append("triple kill")
        elif event_type == "objective_clutch":
            if "clutch" not in tags:
                tags.append("clutch")
            if "overtime" not in tags:
                tags.append("overtime")
        elif event_type == "crown_victory":
            for t in ("Crown", "Winner", "Fall Guys Crown"):
                if t not in tags:
                    tags.append(t)
        elif event_type == "round_qualified":
            for t in ("Qualified", "Fall Guys Qualified"):
                if t not in tags:
                    tags.append(t)
        elif event_type == "eliminated":
            for t in ("Eliminated", "Fall Guys Fail"):
                if t not in tags:
                    tags.append(t)

    # 5. Channel name / handle
    channel_name = _clean(getattr(video, "channel_name", None) if video else None)
    if channel_name:
        handle = channel_name.lstrip("@").strip()
        if handle and handle not in tags:
            tags.append(handle)

    # 6. Base gaming tags
    for bt in _BASE_TAGS:
        if bt not in tags:
            tags.append(bt)

    # 7. Shorts tags
    if is_short:
        if "Shorts" not in tags:
            tags.append("Shorts")
        if "YouTubeShorts" not in tags:
            tags.append("YouTubeShorts")

    # De-dup (case-insensitively while preserving original casing) and enforce YouTube budget
    seen: set[str] = set()
    result: list[str] = []
    total_chars = 0
    for t in tags:
        t_clean = t.lstrip("#").strip()
        if not t_clean:
            continue
        lower = t_clean.lower()
        if lower in seen:
            continue
        if len(result) >= 30 or total_chars + len(t_clean) + 1 > 480:
            break
        seen.add(lower)
        result.append(t_clean)
        total_chars += len(t_clean) + 1

    return result


def build_description(
    video: Any = None,
    job: Any = None,
    clip_id: str = "",
    is_short: bool = True,
    candidate: Any = None,
    hero_name: str | None = None,
    clip_context: str | None = None,
    game: str | None = None,
    tags: list[str] | None = None,
) -> str:
    """Build a creator-quality description referencing hero, context, tags, source video, and VOD timestamp."""
    job_meta = _extract_job_meta(job)
    cand_details = _extract_candidate_details(candidate)

    hero = (
        _clean(hero_name)
        or _clean(job_meta.get("hero_name"))
        or _clean(cand_details.get("hero_name"))
        or _clean(cand_details.get("character_name"))
    )
    context = _clean(clip_context) or _clean(job_meta.get("clip_context"))
    game_name = (
        _clean(game)
        or _clean(job_meta.get("game"))
        or _clean(getattr(candidate, "game", None) if candidate else None)
        or _clean(getattr(video, "game", None) if video else None)
    )
    if not game_name and video:
        vtitle = str(getattr(video, "title", "")).lower()
        if "marvel rivals" in vtitle:
            game_name = "Marvel Rivals"
        elif any(k in vtitle for k in ("fall guys", "fall_guys", "fallguys")):
            game_name = "Fall Guys"

    event_type = _clean(getattr(candidate, "event_type", None) if candidate else None)
    if not event_type and cand_details:
        event_type = _clean(cand_details.get("event_type"))

    # Map event label
    event_label = None
    if event_type == "team_wipe" or cand_details.get("is_team_wipe"):
        event_label = "Team Wipe"
    elif event_type == "penta_ko":
        event_label = "Penta KO"
    elif event_type == "quad_ko":
        event_label = "Quad KO"
    elif event_type == "triple_ko":
        event_label = "Triple KO"
    elif event_type == "shutdown":
        event_label = "Ultimate Shutdown"
    elif event_type == "objective_clutch":
        event_label = "Objective Clutch"
    elif event_type == "kill_streak":
        streak = cand_details.get("streak_count") or cand_details.get("kill_count")
        event_label = f"{streak}-Player Streak" if streak else "Kill Streak"
    elif event_type:
        event_label = event_type.replace("_", " ").title()

    lines: list[str] = []

    # 1. Hook Line
    if hero and context:
        lines.append(f"🔥 {hero} with an insane play: {context}!")
    elif context:
        lines.append(f"🔥 {context}!")
    elif hero and event_label:
        lines.append(f"🔥 Epic {hero} {event_label} in {game_name or 'the match'}!")
    elif hero:
        lines.append(
            f"🔥 Unreal {hero} gameplay highlight in {game_name or 'the stream'}!"
        )
    elif event_label:
        lines.append(f"🔥 Insane {event_label} moment in {game_name or 'the game'}!")
    else:
        lines.append("Gameplay highlight rendered with BackseatCaster AI Clip Engine.")

    # 2. Context line if context was not already the entire hook
    if context and (not hero or not lines[0].endswith(f"{context}!")):
        lines.append(f"Context: {context}")

    # 3. Key Highlight Details
    detail_parts: list[str] = []
    if hero:
        detail_parts.append(f"Hero: {hero}")
    if game_name:
        detail_parts.append(f"Game: {game_name}")
    if event_label:
        detail_parts.append(f"Event: {event_label}")

    start_s = _as_int(
        getattr(job, "start_seconds", None)
        if job and getattr(job, "start_seconds", None) is not None
        else (getattr(candidate, "start_seconds", 0.0) if candidate else 0.0),
        0,
    )
    dur_raw = (
        getattr(job, "duration_seconds", None)
        if job and getattr(job, "duration_seconds", None) is not None
        else (getattr(candidate, "duration_seconds", None) if candidate else None)
    )
    dur_s = _as_int(dur_raw, 0)
    if dur_s > 0:
        detail_parts.append(f"Timing: {start_s}s - {start_s + dur_s}s")

    if detail_parts:
        lines.append(" | ".join(detail_parts))

    # 4. Source & VOD Links
    video_title = _clean(getattr(video, "title", None) if video else None)
    channel_name = _clean(getattr(video, "channel_name", None) if video else None)
    webpage_url = _clean(getattr(video, "webpage_url", None) if video else None)

    if channel_name:
        lines.append(f"Clipped from {channel_name}'s stream.")
    if video_title:
        lines.append(f"Source: {video_title}")
    if webpage_url:
        sep = "&" if "?" in webpage_url else "?"
        lines.append(f"Watch the full VOD: {webpage_url}{sep}t={start_s}s")
    if getattr(job, "narration_path", None) if job else None:
        lines.append("Includes AI-generated commentary.")

    # 5. Hashtags Line
    hashtags: list[str] = []
    if is_short:
        hashtags.append("#Shorts")
    if game_name:
        hashtags.append(f"#{game_name.replace(' ', '')}")
    if hero:
        hashtags.append(f"#{hero.replace(' ', '')}")

    all_tags = tags or build_tags(
        video=video,
        job=job,
        is_short=is_short,
        candidate=candidate,
        hero_name=hero,
        game=game_name,
    )
    for t in all_tags:
        clean_tag = re.sub(r"[^a-zA-Z0-9]", "", t)
        if clean_tag and len(clean_tag) > 1:
            ht = f"#{clean_tag}"
            if ht.lower() not in {h.lower() for h in hashtags} and len(hashtags) < 7:
                hashtags.append(ht)

    lines.append("")
    lines.append(" ".join(hashtags))

    return "\n".join(lines).strip()


def generate_upload_metadata(
    video: Any = None,
    job: Any = None,
    candidate: Any = None,
    clip_id: str = "",
    preferred_format: str | None = None,
    existing: dict[str, Any] | None = None,
    is_short_hint: bool | None = None,
    hero_name: str | None = None,
    clip_context: str | None = None,
    game: str | None = None,
) -> dict[str, Any]:
    """Return a fully-populated upload metadata dict incorporating hero, context, and candidate details."""
    existing = existing or {}
    job_meta = _extract_job_meta(job)
    cand_details = _extract_candidate_details(candidate)

    resolved_hero = (
        _clean(hero_name)
        or _clean(existing.get("hero_name"))
        or _clean(job_meta.get("hero_name"))
        or _clean(cand_details.get("hero_name"))
        or _clean(cand_details.get("character_name"))
    )
    resolved_context = (
        _clean(clip_context)
        or _clean(existing.get("clip_context"))
        or _clean(job_meta.get("clip_context"))
    )
    resolved_game = (
        _clean(game)
        or _clean(existing.get("game"))
        or _clean(job_meta.get("game"))
        or _clean(getattr(candidate, "game", None) if candidate else None)
        or _clean(getattr(video, "game", None) if video else None)
    )

    fmt = (
        preferred_format
        or (getattr(job, "selected_format", None) if job else None)
        or existing.get("preferred_format")
        or "vertical_blur"
    )
    is_vertical = fmt != "landscape"
    duration = (
        getattr(job, "duration_seconds", None)
        if job
        else (getattr(candidate, "duration_seconds", None) if candidate else None)
    )
    try:
        dur_val = float(duration) if duration is not None else 15.0
    except (TypeError, ValueError):
        dur_val = 15.0
    is_short = (
        is_short_hint
        if is_short_hint is not None
        else (is_vertical and dur_val <= 60.0)
    )

    tags = existing.get("tags")
    if not isinstance(tags, list) or not tags:
        tags = build_tags(
            video=video,
            job=job,
            is_short=bool(is_short),
            candidate=candidate,
            hero_name=resolved_hero,
            game=resolved_game,
        )
    else:
        tags = [str(t).strip() for t in tags if str(t).strip()]

    title = _clean(existing.get("title"))
    if title is None:
        title = build_title(
            video=video,
            job=job,
            clip_id=clip_id,
            candidate=candidate,
            hero_name=resolved_hero,
            clip_context=resolved_context,
            game=resolved_game,
            is_short=bool(is_short),
        )

    description = _clean(existing.get("description"))
    if description is None:
        description = build_description(
            video=video,
            job=job,
            clip_id=clip_id,
            is_short=bool(is_short),
            candidate=candidate,
            hero_name=resolved_hero,
            clip_context=resolved_context,
            game=resolved_game,
            tags=tags,
        )

    privacy = _clean(existing.get("privacy")) or "public"

    return {
        "is_selected": bool(existing.get("is_selected", False)),
        "preferred_format": fmt,
        "title": title,
        "description": description,
        "tags": tags,
        "privacy": privacy,
        "hero_name": resolved_hero,
        "clip_context": resolved_context,
        "game": resolved_game,
        "updated_at": datetime.now(UTC).isoformat(),
    }


# Backwards-compatible alias for callers expecting the older helper name.
generate_default_metadata = generate_upload_metadata
