"""LLM-generated YouTube Shorts metadata (title, description, tags).

Supports any OpenAI-compatible API (local Ollama, LM Studio, Groq, OpenAI, Gemini).
Every call degrades gracefully to the deterministic
:mod:`app.services.upload_metadata` generator when disabled, unconfigured,
the request fails, or the model returns unusable text.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
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
Extra context: {clip_context}

Rules:
- title: at most 60-70 characters, punchy and specific. Feature the hero and key action
  (kills/streak/ultimate/objective play) prominently when known. Include 1-2 relevant gaming action emojis
  (such as 🔥, ⚡️, 💥, 🎯, 🛑, 🚀, 👑, 🏆) to make the title stand out on mobile feeds. No clickbait
  that contradicts the facts, no quotes around it. Do not include #Shorts.
- description: 2-4 short lines. First line is an engaging hook highlighting the hero or play.
  Mention the source video/channel when known. End with a line of 4-6 relevant hashtags
  (include #Shorts, hero name when known, and the game name when known).
- tags: 8-15 short lowercase-or-title-case keywords including the hero, game, and action type, no leading '#'.
- Return ONLY JSON matching the schema.
"""

_KNOWN_HEROES_CACHE: list[str] | None = None


def get_known_heroes() -> list[str]:
    """Load known hero names from hero_templates/heroes.json or return default list."""
    global _KNOWN_HEROES_CACHE
    if _KNOWN_HEROES_CACHE is not None:
        return _KNOWN_HEROES_CACHE
    heroes: list[str] = []
    candidates_paths = [
        settings.hero_templates_path / "heroes.json",
        settings.hero_templates_path / "marvel_rivals" / "heroes.json",
        Path("data/hero_templates/heroes.json"),
    ]
    for p in candidates_paths:
        if p.is_file():
            try:
                with open(p, encoding="utf-8") as f:
                    data = json.load(f)
                items = data.get("heroes") if isinstance(data, dict) else None
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict) and item.get("hero_display"):
                            heroes.append(item["hero_display"].strip())
                if heroes:
                    break
            except Exception as e:
                logger.debug("Failed loading heroes.json from %s: %s", p, e)

    if not heroes:
        heroes = [
            "Magneto",
            "Luna Snow",
            "Spider-Man",
            "Iron Man",
            "Hulk",
            "Venom",
            "Doctor Strange",
            "Black Panther",
            "The Punisher",
            "Punisher",
            "Hela",
            "Scarlet Witch",
            "Magik",
            "Groot",
            "Rocket Raccoon",
            "Star-Lord",
            "Mantis",
            "Storm",
            "Thor",
            "Captain America",
            "Winter Soldier",
            "Loki",
            "Adam Warlock",
            "Peni Parker",
            "Namor",
            "Jeff the Land Shark",
            "Psylocke",
            "Moon Knight",
            "Hawkeye",
            "Cloak & Dagger",
            "Iron Fist",
            "Wolverine",
            "Invisible Woman",
            "Mister Fantastic",
            "Human Torch",
            "The Thing",
            "Black Widow",
            "Blade",
        ]
    _KNOWN_HEROES_CACHE = heroes
    return _KNOWN_HEROES_CACHE


def infer_hero_name(*texts: Any) -> str | None:
    """Scan text strings for mention of any known hero."""
    heroes = get_known_heroes()
    combined = " ".join(str(t) for t in texts if t)
    if not combined.strip():
        return None
    for hero in heroes:
        pattern = rf"\b{re.escape(hero)}\b"
        if re.search(pattern, combined, flags=re.IGNORECASE):
            return hero
    return None


class _LLMMetadata(BaseModel):
    """Structured Gemini response schema."""

    title: str = Field(
        description="YouTube Shorts title with 1-2 gaming action emojis, at most 60-70 characters"
    )
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
    """Universal OpenAI-compatible upload metadata generator with deterministic fallback."""

    @classmethod
    def is_available(cls) -> bool:
        """True when AI copy should be used by default (enabled + provider configured)."""
        return bool(settings.LLM_METADATA_ENABLED and cls.is_configured())

    @staticmethod
    def is_configured() -> bool:
        """True when an LLM provider is configured (API key exists or custom base URL is set)."""
        if settings.llm_api_key:
            return True
        if settings.LLM_BASE_URL:
            return True
        return False

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
        force_source: str | None = None,
        hero_name: str | None = None,
        clip_context: str | None = None,
        game: str | None = None,
    ) -> dict[str, Any]:
        """Return a complete upload metadata dict tagged with its source.

        ``force_source`` overrides the default selection: ``"llm"`` always
        attempts Gemini (still degrading to the deterministic generator when
        the key or SDK is unavailable), ``"fallback"`` always uses the
        deterministic generator, and ``None`` follows server configuration.
        """
        existing = existing or {}
        fallback = generate_upload_metadata(
            video=video,
            job=job,
            candidate=candidate,
            clip_id=clip_id,
            preferred_format=preferred_format,
            existing=existing,
            is_short_hint=is_short,
            hero_name=hero_name,
            clip_context=clip_context,
            game=game,
        )

        if force_source == "fallback":
            fallback["metadata_source"] = "fallback"
            return fallback
        if force_source != "llm" and not cls.is_available():
            fallback["metadata_source"] = "fallback"
            return fallback

        prompt = cls._build_prompt(
            video=video,
            job=job,
            candidate=candidate,
            preferred_format=preferred_format,
            hero_name=hero_name,
            clip_context=clip_context,
            game=game,
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
        hero_name: str | None = None,
        clip_context: str | None = None,
        game: str | None = None,
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

        resolved_hero = (
            _clean(hero_name) or _clean(details.get("hero_name")) or "unknown"
        )
        resolved_game = (
            _clean(game)
            or _clean(getattr(candidate, "game", None))
            or _clean(details.get("game"))
            or "gaming"
        )
        resolved_context = _clean(clip_context) or "none"

        return _METADATA_PROMPT.format(
            video_title=_clean(getattr(video, "title", None)) or "(unknown)",
            channel_name=_clean(getattr(video, "channel_name", None)) or "(unknown)",
            game=resolved_game,
            start_seconds=start,
            end_seconds=end,
            duration_seconds=max(0.0, end - start),
            event_type=_clean(getattr(candidate, "event_type", None)) or "highlight",
            hero_name=resolved_hero,
            kill_count=details.get("kill_count") or 0,
            multi_kill_chain=details.get("multi_kill_chain") or "none",
            streak_count=details.get("streak_count") or "none",
            has_ultimate=bool(details.get("has_ultimate")),
            is_team_wipe=bool(details.get("is_team_wipe")),
            game_phase=_clean(details.get("game_phase")) or "regular",
            abilities=", ".join(details.get("abilities_used") or []) or "none detected",
            trigger_events=trigger_labels or "none",
            clip_context=resolved_context,
        )

    @classmethod
    def _call_llm(cls, prompt: str) -> dict[str, Any] | None:
        """Call OpenAI-compatible chat completions endpoint; return None on any failure."""
        api_key = settings.llm_api_key
        base_url = settings.resolved_llm_base_url.rstrip("/")
        url = (
            base_url
            if base_url.endswith("/chat/completions")
            else f"{base_url}/chat/completions"
        )

        headers: dict[str, str] = {
            "Content-Type": "application/json",
        }
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        payload: dict[str, Any] = {
            "model": settings.resolved_llm_model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You write titles, descriptions and tags for YouTube Shorts made from gaming highlights. "
                        "Output strictly a valid JSON object with keys 'title', 'description', and 'tags'. "
                        "Do not include any commentary outside the JSON object."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.7,
            "response_format": {"type": "json_object"},
        }

        try:
            import httpx

            with httpx.Client(timeout=30.0) as client:
                resp = client.post(url, headers=headers, json=payload)
                # Some local / non-OpenAI endpoints don't accept response_format
                if resp.status_code == 400 and "response_format" in resp.text:
                    payload.pop("response_format", None)
                    resp = client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.warning("LLM metadata generation failed: %s", exc)
            return None

        choices = data.get("choices") or []
        if not choices:
            logger.warning("LLM response contained no choices: %s", data)
            return None

        content = choices[0].get("message", {}).get("content", "")
        if not content:
            logger.warning("LLM response message content was empty")
            return None

        return cls._parse_json_response(content)

    @classmethod
    def _call_gemini(cls, prompt: str) -> dict[str, Any] | None:
        """Alias for _call_llm for backwards compatibility with tests and callers."""
        return cls._call_llm(prompt)

    @classmethod
    def _parse_json_response(cls, text: str) -> dict[str, Any] | None:
        """Parse JSON response from LLM, handling markdown code blocks and raw text."""
        cleaned_text = _clean(text)
        if not cleaned_text:
            return None

        # 1. Direct JSON parse
        try:
            data = json.loads(cleaned_text)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

        # 2. Strip markdown fences (e.g. ```json ... ```)
        unfenced = re.sub(
            r"^```(?:json)?\s*", "", cleaned_text, flags=re.IGNORECASE
        ).strip()
        unfenced = re.sub(r"\s*```$", "", unfenced).strip()
        try:
            data = json.loads(unfenced)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

        # 3. Fallback regex to capture outer {...} block
        match = re.search(r"\{[\s\S]*\}", cleaned_text)
        if match:
            try:
                data = json.loads(match.group(0))
                if isinstance(data, dict):
                    return data
            except json.JSONDecodeError:
                pass

        logger.warning("LLM metadata response was not valid JSON: %s", cleaned_text)
        return None

    @classmethod
    def regenerate_clip_metadata(
        cls,
        db: Any,
        clip_id: str,
        *,
        use_llm: bool | None = None,
        hero_name: str | None = None,
        clip_context: str | None = None,
        game: str | None = None,
        highlight_candidate_id: str | None = None,
    ) -> dict[str, Any]:
        """Regenerate title/description/tags for an existing rendered clip.

        The render itself is untouched: only the staged upload copy is
        rewritten (privacy, schedule and queue selection are preserved), and
        the replaced copy is stored as ``previous_metadata`` so the creator can
        compare AI and non-AI outputs side by side.
        """
        # Local imports keep the service graph acyclic (renders <-> metadata).
        from app.models.highlight_candidate import HighlightCandidate
        from app.models.render_job import RenderJob
        from app.models.video import Video
        from app.schemas.render import UploadSelectionRequest
        from app.services.renders import RenderService

        job = (
            db.query(RenderJob)
            .filter((RenderJob.clip_id == clip_id) | (RenderJob.id == clip_id))
            .first()
        )
        if job is None:
            raise FileNotFoundError(f"Rendered clip '{clip_id}' not found.")

        current: dict[str, Any] = {}
        if job.upload_metadata:
            try:
                parsed = json.loads(job.upload_metadata)
                if isinstance(parsed, dict):
                    current = parsed
            except Exception:
                current = {}

        video = (
            db.query(Video).filter(Video.id == job.video_id).first()
            if job.video_id
            else None
        )
        candidate: Any = None
        candidate_id = (
            highlight_candidate_id
            or job.highlight_candidate_id
            or current.get("highlight_candidate_id")
        )
        if candidate_id:
            candidate = (
                db.query(HighlightCandidate)
                .filter(HighlightCandidate.id == str(candidate_id))
                .first()
            )

        # Automatic candidate fallback: look up overlapping candidate window by timestamp
        if candidate is None and job.video_id and job.start_seconds is not None:
            job_start = float(job.start_seconds)
            job_dur = float(job.duration_seconds or 15.0)
            job_end = job_start + job_dur
            candidates = (
                db.query(HighlightCandidate)
                .filter(HighlightCandidate.video_id == job.video_id)
                .all()
            )
            best_cand = None
            min_dist = float("inf")
            for c in candidates:
                # Check direct temporal overlap or start proximity within 15 seconds
                is_overlap = c.start_seconds < job_end and c.end_seconds > job_start
                dist = abs(c.start_seconds - job_start)
                if is_overlap or dist <= 15.0:
                    if dist < min_dist:
                        min_dist = dist
                        best_cand = c
            if best_cand:
                candidate = best_cand
                job.highlight_candidate_id = best_cand.id

        cand_details = _details_from_candidate(candidate)
        resolved_hero = (
            _clean(hero_name)
            or _clean(current.get("hero_name"))
            or _clean(cand_details.get("hero_name"))
            or infer_hero_name(
                current.get("title"),
                getattr(video, "title", None),
                getattr(candidate, "suggested_title", None),
            )
        )
        resolved_context = _clean(clip_context) or _clean(current.get("clip_context"))
        resolved_game = (
            _clean(game)
            or _clean(current.get("game"))
            or _clean(getattr(candidate, "game", None))
            or _clean(cand_details.get("game"))
        )

        previous = {
            "title": current.get("title"),
            "description": current.get("description"),
            "tags": current.get("tags") or [],
            "metadata_source": current.get("metadata_source", "fallback"),
            "hero_name": current.get("hero_name"),
            "clip_context": current.get("clip_context"),
        }

        preferred_format = (
            job.selected_format or current.get("preferred_format") or "vertical_blur"
        )
        try:
            duration = float(job.duration_seconds) if job.duration_seconds else 15.0
        except (TypeError, ValueError):
            duration = 15.0
        is_short = preferred_format != "landscape" and duration <= 60.0

        force_source = None if use_llm is None else ("llm" if use_llm else "fallback")
        metadata = cls.generate_clip_metadata(
            video=video,
            job=job,
            candidate=candidate,
            clip_id=job.clip_id,
            preferred_format=preferred_format,
            existing={},
            is_short=is_short,
            force_source=force_source,
            hero_name=resolved_hero,
            clip_context=resolved_context,
            game=resolved_game,
        )

        RenderService.update_upload_selection(
            db,
            job.clip_id,
            UploadSelectionRequest(
                is_selected=bool(job.is_selected_for_upload)
                or bool(current.get("is_selected")),
                preferred_format=preferred_format,
                title=metadata.get("title"),
                description=metadata.get("description"),
                tags=metadata.get("tags") or [],
                # Preserve the staged privacy (private when a schedule exists).
                privacy=current.get("privacy") or "public",
            ),
        )

        # update_upload_selection rebuilds the dict, so re-attach provenance,
        # schedule, hero and context details for future regenerations.
        db.refresh(job)
        patched: dict[str, Any] = {}
        try:
            patched = json.loads(job.upload_metadata or "{}") or {}
        except Exception:
            patched = {}
        patched["metadata_source"] = metadata.get("metadata_source", "fallback")
        if job.scheduled_publish_at is not None:
            patched["scheduled_publish_at"] = job.scheduled_publish_at.isoformat()
        if job.highlight_candidate_id:
            patched["highlight_candidate_id"] = job.highlight_candidate_id
        if candidate and getattr(candidate, "score", None) is not None:
            patched["highlight_score"] = float(candidate.score)
        elif current.get("highlight_score") is not None:
            patched["highlight_score"] = current["highlight_score"]
        if resolved_hero:
            patched["hero_name"] = resolved_hero
        if resolved_context:
            patched["clip_context"] = resolved_context
        if resolved_game:
            patched["game"] = resolved_game

        if any(previous.get(k) for k in ("title", "description", "tags")):
            patched["previous_metadata"] = {
                **previous,
                "regenerated_at": datetime.now(UTC).isoformat(),
            }
        job.upload_metadata = json.dumps(patched)
        db.commit()
        db.refresh(job)

        source = str(patched.get("metadata_source", "fallback"))
        logger.info(
            "Regenerated metadata for %s via %s (use_llm=%s, hero=%s)",
            clip_id,
            source,
            use_llm,
            resolved_hero,
        )
        return {
            "clip_id": job.clip_id,
            "metadata_source": source,
            "used_llm": source == "llm",
            "llm_available": cls.is_configured(),
            "upload_selection": patched,
            "previous": patched.get("previous_metadata") or previous,
            "message": (
                "Metadata regenerated with AI copy."
                if source == "llm"
                else "Metadata regenerated with deterministic copy."
            ),
        }
