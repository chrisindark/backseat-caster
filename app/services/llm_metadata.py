"""LLM-generated YouTube Shorts metadata (title, description, tags).

Phase 8 conditions Gemini on the mined highlight context (hero, multi-kill
chain, ultimate payoff, game phase) to produce mobile-optimised copy. Every
call degrades gracefully to the deterministic
:mod:`app.services.upload_metadata` generator when the API key is missing,
the SDK is unavailable, the request fails, or the model returns unusable text.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from pydantic import BaseModel, Field

from app.config import settings
from app.services.upload_metadata import generate_upload_metadata

logger = logging.getLogger(__name__)

MAX_TITLE_LENGTH = 100
MAX_DESCRIPTION_LENGTH = 5000
MAX_TAG_COUNT = 30

_METADATA_PROMPT = """You write titles, descriptions and tags for YouTube Shorts
made from gaming highlights. Use only the facts below; never invent kills,
heroes, abilities or scores that are not listed.

Source video: {video_title}
Channel: {channel_name}
Game: {game}
Clip window: {start_seconds:.1f}s to {end_seconds:.1f}s ({duration_seconds:.1f}s)
Detected event: {event_type}
Hero: {hero_name}
Kills in clip: {kill_count}
Multi-kill chain: {multi_kill_chain}
Player streak: {streak_count}
Ultimate cast: {has_ultimate}
Team wipe: {is_team_wipe}
Game phase: {game_phase}
Abilities used: {abilities}
Trigger events: {trigger_events}

Rules:
- title: at most 50 characters, punchy and specific. No emojis, no clickbait
  that contradicts the facts, no quotes around it. Do not include #Shorts.
- description: 2-4 short lines. First line is a hook. Mention the source
  video/channel when known. End with a line of 4-6 relevant hashtags
  (include #Shorts and the game name when known).
- tags: 8-15 short lowercase-or-title-case keywords, no leading '#'.
- Return ONLY JSON matching the schema.
"""


class _LLMMetadata(BaseModel):
    """Structured Gemini response schema."""

    title: str = Field(description="YouTube Shorts title, at most 50 characters")
    description: str = Field(description="Punchy multi-line description with hashtags")
    tags: list[str] = Field(
        default_factory=list, description="Keyword tags without '#'"
    )


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _details_from_candidate(candidate: Any) -> dict[str, Any]:
    """Extract HighlightDetails from a model, dict, or JSON string."""
    if candidate is None:
        return {}
    raw = getattr(candidate, "details_json", None)
    if raw:
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    details = getattr(candidate, "details", None)
    if isinstance(details, dict):
        return details
    if isinstance(candidate, dict):
        nested = candidate.get("details")
        if isinstance(nested, dict):
            return nested
        return candidate
    return {}


def _normalise_title(raw: str | None, fallback: str) -> str:
    title = _clean(raw) or fallback
    title = title.strip("\"'\u201c\u201d ")
    title = re.sub(r"\s+", " ", title)
    if len(title) > MAX_TITLE_LENGTH:
        title = title[: MAX_TITLE_LENGTH - 3].rstrip() + "..."
    return title or fallback


def _normalise_tags(raw: Any, fallback: list[str], is_short: bool) -> list[str]:
    tags: list[str] = []
    if isinstance(raw, list):
        for item in raw:
            tag = _clean(item)
            if not tag:
                continue
            tag = tag.lstrip("#").strip()
            if tag and tag.lower() not in {t.lower() for t in tags}:
                tags.append(tag)
    for tag in fallback:
        tag = tag.lstrip("#").strip()
        if tag and tag.lower() not in {t.lower() for t in tags}:
            tags.append(tag)
    if is_short and not any(t.lower() == "shorts" for t in tags):
        tags.append("Shorts")
    return tags[:MAX_TAG_COUNT]


def _normalise_description(raw: str | None, fallback: str, tags: list[str]) -> str:
    description = _clean(raw) or fallback
    description = description.strip()
    if "#" not in description:
        hashtags = " ".join(f"#{t.replace(' ', '')}" for t in tags[:6])
        if hashtags:
            description = f"{description}\n\n{hashtags}"
    return description[:MAX_DESCRIPTION_LENGTH]


class LLMMetadataService:
    """Gemini-powered upload metadata generator with deterministic fallback."""

    @staticmethod
    def is_available() -> bool:
        return bool(settings.LLM_METADATA_ENABLED and settings.gemini_api_key)

    @classmethod
    def generate_clip_metadata(
        cls,
        *,
        video: Any = None,
        job: Any = None,
        candidate: Any = None,
        clip_id: str = "",
        preferred_format: str = "vertical_blur",
        existing: dict[str, Any] | None = None,
        is_short: bool = True,
    ) -> dict[str, Any]:
        """Return a complete upload metadata dict tagged with its source."""
        existing = existing or {}
        fallback = generate_upload_metadata(
            video=video,
            job=job,
            clip_id=clip_id,
            preferred_format=preferred_format,
            existing=existing,
            is_short_hint=is_short,
        )

        if not cls.is_available():
            fallback["metadata_source"] = "fallback"
            return fallback

        prompt = cls._build_prompt(
            video=video,
            job=job,
            candidate=candidate,
            preferred_format=preferred_format,
        )
        generated = cls._call_gemini(prompt)
        if generated is None:
            fallback["metadata_source"] = "fallback"
            return fallback

        tags = _normalise_tags(
            generated.get("tags"), fallback.get("tags") or [], is_short
        )
        return {
            **fallback,
            "title": _normalise_title(
                generated.get("title"), fallback.get("title") or ""
            ),
            "description": _normalise_description(
                generated.get("description"),
                fallback.get("description") or "",
                tags,
            ),
            "tags": tags,
            "metadata_source": "llm",
        }

    @staticmethod
    def _build_prompt(
        *,
        video: Any = None,
        job: Any = None,
        candidate: Any = None,
        preferred_format: str = "vertical_blur",
    ) -> str:
        details = _details_from_candidate(candidate)
        start = float(
            getattr(candidate, "start_seconds", None)
            if candidate is not None
            and getattr(candidate, "start_seconds", None) is not None
            else (getattr(job, "start_seconds", 0.0) or 0.0)
        )
        end = float(
            getattr(candidate, "end_seconds", None)
            if candidate is not None
            and getattr(candidate, "end_seconds", None) is not None
            else start + float(getattr(job, "duration_seconds", 15.0) or 15.0)
        )
        triggers = details.get("trigger_events") or []
        trigger_labels = ", ".join(
            str(t.get("label", ""))
            for t in triggers
            if isinstance(t, dict) and t.get("label")
        )
        return _METADATA_PROMPT.format(
            video_title=_clean(getattr(video, "title", None)) or "(unknown)",
            channel_name=_clean(getattr(video, "channel_name", None)) or "(unknown)",
            game=_clean(getattr(candidate, "game", None))
            or _clean(details.get("game"))
            or "gaming",
            start_seconds=start,
            end_seconds=end,
            duration_seconds=max(0.0, end - start),
            event_type=_clean(getattr(candidate, "event_type", None)) or "highlight",
            hero_name=_clean(details.get("hero_name")) or "unknown",
            kill_count=details.get("kill_count") or 0,
            multi_kill_chain=details.get("multi_kill_chain") or "none",
            streak_count=details.get("streak_count") or "none",
            has_ultimate=bool(details.get("has_ultimate")),
            is_team_wipe=bool(details.get("is_team_wipe")),
            game_phase=_clean(details.get("game_phase")) or "regular",
            abilities=", ".join(details.get("abilities_used") or []) or "none detected",
            trigger_events=trigger_labels or "none",
        )

    @staticmethod
    def _call_gemini(prompt: str) -> dict[str, Any] | None:
        """Call Gemini with a JSON schema; return None on any failure."""
        api_key = settings.gemini_api_key
        if not api_key:
            return None
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=_LLMMetadata,
                    temperature=0.9,
                    max_output_tokens=1024,
                ),
            )
        except Exception as exc:
            logger.warning("Gemini metadata generation failed: %s", exc)
            return None

        text = _clean(getattr(response, "text", None))
        if not text:
            logger.warning("Gemini metadata response was empty")
            return None
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Gemini metadata response was not valid JSON")
            return None
        return data if isinstance(data, dict) else None
