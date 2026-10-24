"""Autonomous Phase 8 staging pipeline.

After highlight clustering completes, the top-scoring candidates can be
rendered as vertical Shorts, enriched with LLM metadata, marked for upload and
assigned staggered native ``publishAt`` slots. The creator reviews the staged
queue and publishes immediately or edits the schedule.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.models.highlight_candidate import HighlightCandidate
from app.models.render_job import RenderJob
from app.models.video import Video
from app.schemas.render import RenderClipRequest, UploadSelectionRequest
from app.services.llm_metadata import LLMMetadataService
from app.services.renders import RenderService

logger = logging.getLogger(__name__)

VERTICAL_MODES = (
    "third_person",
    "direct_crop",
    "cinematic",
    "custom",
    "vertical_crop",
    "vertical_blur",
)


def as_utc(value: datetime | None) -> datetime | None:
    """Normalise SQLite-naive or aware datetimes to aware UTC."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class AutoStageService:
    """Render, enrich and schedule the best highlights automatically."""

    @staticmethod
    def next_publish_slot(db: Session, now: datetime | None = None) -> datetime:
        """Return the next staggered publish slot after any already scheduled clip."""
        current = now or datetime.now(UTC)
        first = current + timedelta(hours=settings.AUTO_STAGE_FIRST_SLOT_HOURS)
        interval = timedelta(hours=max(1, settings.AUTO_STAGE_INTERVAL_HOURS))

        latest = (
            db.query(func.max(RenderJob.scheduled_publish_at))
            .filter(RenderJob.scheduled_publish_at.isnot(None))
            .scalar()
        )
        latest_utc = as_utc(latest)
        if latest_utc and latest_utc >= first:
            return latest_utc + interval
        return first

    @classmethod
    def stage_top_candidates(
        cls,
        db: Session,
        video_id: str,
        *,
        top_n: int | None = None,
        min_score: float | None = None,
        clipping_mode: str | None = None,
        schedule: bool = True,
        background_tasks: Any = None,
    ) -> dict[str, Any]:
        """Stage the top N candidates for a video and return a summary."""
        video = db.query(Video).filter(Video.id == video_id).first()
        if not video:
            raise ValueError(f"Video '{video_id}' not found")

        count = max(0, int(top_n if top_n is not None else settings.AUTO_STAGE_TOP_N))
        threshold = float(
            min_score if min_score is not None else settings.AUTO_STAGE_MIN_SCORE
        )
        mode = clipping_mode or settings.AUTO_STAGE_CLIPPING_MODE
        if mode not in VERTICAL_MODES:
            mode = "third_person"

        if count == 0:
            return {
                "video_id": video_id,
                "staged_count": 0,
                "clips": [],
                "message": "Auto-stage disabled (top_n=0).",
            }

        candidates = (
            db.query(HighlightCandidate)
            .filter(
                HighlightCandidate.video_id == video_id,
                HighlightCandidate.score >= threshold,
            )
            .order_by(HighlightCandidate.score.desc(), HighlightCandidate.start_seconds)
            .limit(count)
            .all()
        )

        already_staged = {
            row[0]
            for row in db.query(RenderJob.highlight_candidate_id)
            .filter(
                RenderJob.video_id == video_id,
                RenderJob.highlight_candidate_id.isnot(None),
            )
            .all()
            if row[0]
        }

        staged: list[dict[str, Any]] = []
        slot = cls.next_publish_slot(db) if schedule else None

        for candidate in candidates:
            if candidate.id in already_staged:
                logger.info(
                    "Skipping auto-stage for %s: candidate already staged",
                    candidate.id,
                )
                continue

            try:
                summary = cls._stage_candidate(
                    db,
                    video=video,
                    candidate=candidate,
                    mode=mode,
                    slot=slot,
                    background_tasks=background_tasks,
                )
            except Exception as exc:
                logger.warning(
                    "Auto-stage failed for candidate %s (video %s): %s",
                    candidate.id,
                    video_id,
                    exc,
                )
                db.rollback()
                continue

            staged.append(summary)
            if slot is not None:
                slot = slot + timedelta(hours=max(1, settings.AUTO_STAGE_INTERVAL_HOURS))

        message = (
            f"Auto-staged {len(staged)} clip(s) from the top candidates."
            if staged
            else "No candidates met the auto-stage criteria."
        )
        logger.info("Auto-stage for video %s: %s", video_id, message)
        return {
            "video_id": video_id,
            "staged_count": len(staged),
            "clips": staged,
            "message": message,
        }

    @classmethod
    def _stage_candidate(
        cls,
        db: Session,
        *,
        video: Video,
        candidate: HighlightCandidate,
        mode: str,
        slot: datetime | None,
        background_tasks: Any = None,
    ) -> dict[str, Any]:
        clip_id = f"auto_{candidate.id}"
        existing_job = (
            db.query(RenderJob).filter(RenderJob.clip_id == clip_id).first()
        )
        if existing_job:
            raise RuntimeError("clip already exists")

        duration = min(60.0, max(3.0, float(candidate.duration_seconds or 15.0)))
        request = RenderClipRequest(
            video_id=video.id,
            start_seconds=float(candidate.start_seconds),
            duration_seconds=duration,
            clip_id=clip_id,
            crop_preset=(
                mode if mode in ("third_person", "direct_crop", "cinematic", "custom")
                else "third_person"
            ),
            modes=[mode],
            sync=False,
        )

        rendered = RenderService.create_render(
            db=db, request=request, background_tasks=background_tasks
        )
        if not rendered.job_id:
            raise RuntimeError("render job was not created")

        job = db.query(RenderJob).filter(RenderJob.id == rendered.job_id).first()
        if not job:
            raise RuntimeError("render job record disappeared")

        job.auto_staged = True
        job.highlight_candidate_id = candidate.id
        if slot is not None:
            job.scheduled_publish_at = slot
        db.commit()

        metadata = LLMMetadataService.generate_clip_metadata(
            video=video,
            job=job,
            candidate=candidate,
            clip_id=clip_id,
            preferred_format=mode,
            is_short=duration <= 60.0,
        )
        privacy = "private" if slot is not None else metadata.get("privacy", "public")
        RenderService.update_upload_selection(
            db,
            clip_id,
            UploadSelectionRequest(
                is_selected=True,
                preferred_format=metadata.get("preferred_format") or mode,
                title=metadata.get("title"),
                description=metadata.get("description"),
                tags=metadata.get("tags") or [],
                privacy=privacy,
            ),
        )

        # Persist scheduling + provenance alongside the staged metadata.
        db.refresh(job)
        staged_meta: dict[str, Any] = {}
        try:
            staged_meta = json.loads(job.upload_metadata or "{}")
        except Exception:
            staged_meta = {}
        staged_meta["metadata_source"] = metadata.get("metadata_source", "fallback")
        staged_meta["scheduled_publish_at"] = (
            slot.isoformat() if slot is not None else None
        )
        staged_meta["highlight_candidate_id"] = candidate.id
        staged_meta["highlight_score"] = candidate.score
        job.upload_metadata = json.dumps(staged_meta)
        db.commit()

        return {
            "clip_id": clip_id,
            "candidate_id": candidate.id,
            "video_id": video.id,
            "score": float(candidate.score),
            "title": staged_meta.get("title") or "",
            "is_selected_for_upload": True,
            "scheduled_publish_at": slot.isoformat() if slot is not None else None,
            "metadata_source": staged_meta["metadata_source"],
        }
