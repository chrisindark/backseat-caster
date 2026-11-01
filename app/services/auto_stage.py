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
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.models.highlight_candidate import HighlightCandidate
from app.models.render_job import RenderJob
from app.models.video import Video
from app.schemas.render import RenderClipRequest, UploadSelectionRequest
from app.services.channel_profile import ChannelProfileService
from app.services.llm_metadata import LLMMetadataService
from app.services.renders import RenderService
from app.services.upload_metadata import apply_title_template

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


def _parse_time_slot(slot_str: str) -> tuple[int, int] | None:
    """Parse 'HH:MM' or 'H:MM' string into (hour, minute)."""
    parts = slot_str.strip().split(":")
    if len(parts) == 2:
        try:
            h, m = int(parts[0]), int(parts[1])
            if 0 <= h < 24 and 0 <= m < 60:
                return h, m
        except ValueError:
            pass
    return None


def _get_target_timezone(tz_name: str | None = None) -> ZoneInfo:
    """Resolve a configured timezone or fall back to UTC."""
    candidate = (
        tz_name or (getattr(settings, "AUTO_STAGE_TIMEZONE", "") or "")
    ).strip()
    if candidate:
        try:
            return ZoneInfo(candidate)
        except Exception as e:
            logger.warning(
                "Invalid AUTO_STAGE_TIMEZONE '%s': %s, falling back to UTC",
                candidate,
                e,
            )
    return ZoneInfo("UTC")


class AutoStageService:
    """Render, enrich and schedule the best highlights automatically."""

    @classmethod
    def next_publish_slot(
        cls,
        db: Session,
        now: datetime | None = None,
        after: datetime | None = None,
        booked_slots: set[datetime] | None = None,
    ) -> datetime:
        """Return the next publish slot for a staged clip.

        If AUTO_STAGE_DAILY_SLOTS is configured, picks the next chronological daily time slot
        in AUTO_STAGE_TIMEZONE (e.g. Asia/Kolkata), rolling over across days and skipping booked slots.
        Otherwise falls back to the legacy +AUTO_STAGE_INTERVAL_HOURS offset.
        """
        current_utc = as_utc(now) or datetime.now(UTC)
        slots_list, tz_name = ChannelProfileService.schedule_config(db)
        parsed_slots: list[tuple[int, int]] = []
        for s in slots_list:
            parsed = _parse_time_slot(s)
            if parsed:
                parsed_slots.append(parsed)
        parsed_slots.sort()

        # If no daily slots defined, use legacy relative interval
        if not parsed_slots:
            first = current_utc + timedelta(hours=settings.AUTO_STAGE_FIRST_SLOT_HOURS)
            interval = timedelta(hours=max(1, settings.AUTO_STAGE_INTERVAL_HOURS))
            if after is not None:
                return as_utc(after) + interval
            latest = (
                db.query(func.max(RenderJob.scheduled_publish_at))
                .filter(RenderJob.scheduled_publish_at.isnot(None))
                .scalar()
            )
            latest_utc = as_utc(latest)
            if latest_utc and latest_utc >= first:
                return latest_utc + interval
            return first

        # Daily slots mode (e.g. Asia/Kolkata)
        tz = _get_target_timezone(tz_name)
        booked: set[datetime] = set(booked_slots or ())
        if not booked:
            rows = (
                db.query(RenderJob.scheduled_publish_at)
                .filter(RenderJob.scheduled_publish_at.isnot(None))
                .all()
            )
            for r in rows:
                dt_utc = as_utc(r[0])
                if dt_utc:
                    booked.add(dt_utc)

        # Buffer: at least 15 minutes from current time
        min_buffer = timedelta(minutes=15)
        earliest_allowed = current_utc + min_buffer
        if after is not None:
            earliest_allowed = max(
                earliest_allowed, as_utc(after) + timedelta(minutes=1)
            )

        local_ref = earliest_allowed.astimezone(tz)
        candidate_date = local_ref.date()

        for _ in range(365):
            for h, m in parsed_slots:
                local_slot = datetime(
                    candidate_date.year,
                    candidate_date.month,
                    candidate_date.day,
                    h,
                    m,
                    0,
                    tzinfo=tz,
                )
                slot_utc = local_slot.astimezone(UTC)
                if slot_utc < earliest_allowed:
                    continue

                # Collision check within 10 minutes tolerance
                is_collision = any(
                    abs((slot_utc - b).total_seconds()) < 600 for b in booked
                )
                if not is_collision:
                    return slot_utc

            candidate_date += timedelta(days=1)

        return earliest_allowed + timedelta(hours=1)

    @classmethod
    def compute_batch_publish_slots(
        cls,
        db: Session,
        count: int,
        *,
        same_day_catchup: bool = True,
        now: datetime | None = None,
        booked_slots: set[datetime] | None = None,
    ) -> list[datetime]:
        """Compute chronological publishAt timestamps for a batch of clips.

        When same_day_catchup is True and AUTO_STAGE_DAILY_SLOTS is configured in AUTO_STAGE_TIMEZONE:
        If generation happens after some of today's slots have passed (e.g. at 13:51, missing 08:00 and 12:30),
        the missed items catch up at the immediate next available slot (spaced by subtle 3-minute intervals)
        so that all `count` clips are scheduled for publication on the SAME DAY instead of rolling over.
        """
        if count <= 0:
            return []

        current_utc = as_utc(now) or datetime.now(UTC)
        slots_list, tz_name = ChannelProfileService.schedule_config(db)
        parsed_slots: list[tuple[int, int]] = []
        for s in slots_list:
            parsed = _parse_time_slot(s)
            if parsed:
                parsed_slots.append(parsed)
        parsed_slots.sort()

        # If no daily slots defined, fall back to sequential legacy next_publish_slot
        if not parsed_slots:
            allocated: list[datetime] = []
            booked = set(booked_slots or ())
            slot = cls.next_publish_slot(db, now=current_utc, booked_slots=booked)
            for _ in range(count):
                allocated.append(slot)
                booked.add(slot)
                slot = cls.next_publish_slot(
                    db, now=current_utc, after=slot, booked_slots=booked
                )
            return allocated

        tz = _get_target_timezone(tz_name)
        booked = set(booked_slots or ())
        if not booked:
            rows = (
                db.query(RenderJob.scheduled_publish_at)
                .filter(RenderJob.scheduled_publish_at.isnot(None))
                .all()
            )
            for r in rows:
                dt_utc = as_utc(r[0])
                if dt_utc:
                    booked.add(dt_utc)

        min_buffer = timedelta(minutes=15)
        earliest_allowed = current_utc + min_buffer
        local_ref = earliest_allowed.astimezone(tz)
        today = local_ref.date()

        remaining_today: list[datetime] = []
        for h, m in parsed_slots:
            local_slot = datetime(
                today.year, today.month, today.day, h, m, 0, tzinfo=tz
            )
            slot_utc = local_slot.astimezone(UTC)
            if slot_utc >= earliest_allowed:
                remaining_today.append(slot_utc)

        if same_day_catchup and remaining_today:
            allocated = []
            overflow = max(0, count - len(remaining_today))
            catchup_slot = remaining_today[0]
            # Catchup items for missed slots placed at the first available slot, offset by 3 mins
            for i in range(overflow + 1):
                if len(allocated) < count:
                    target = catchup_slot + timedelta(minutes=i * 3)
                    allocated.append(target)
            # Remaining today slots get 1 each
            for s_dt in remaining_today[1:]:
                if len(allocated) < count:
                    allocated.append(s_dt)
            return allocated

        # Sequential rollover fallback if no remaining slots today or same_day_catchup disabled
        allocated = []
        slot = cls.next_publish_slot(db, now=current_utc, booked_slots=booked)
        for _ in range(count):
            allocated.append(slot)
            booked.add(slot)
            slot = cls.next_publish_slot(
                db, now=current_utc, after=slot, booked_slots=booked
            )
        return allocated

    @classmethod
    def stage_selected_candidates(
        cls,
        db: Session,
        video_id: str,
        *,
        candidate_ids: list[str] | None = None,
        top_n: int | None = None,
        min_score: float | None = None,
        clipping_mode: str | None = None,
        schedule: bool = True,
        same_day_catchup: bool = True,
        crop_blur_padding: float | None = None,
        normalize_audio: bool = True,
        background_tasks: Any = None,
    ) -> dict[str, Any]:
        """Stage selected candidate IDs, or auto-pick top N left candidates for a video."""
        video = db.query(Video).filter(Video.id == video_id).first()
        if not video:
            raise ValueError(f"Video '{video_id}' not found")

        profile = ChannelProfileService.get_or_create(db)
        mode = (
            clipping_mode
            or profile.default_framing_preset
            or settings.AUTO_STAGE_CLIPPING_MODE
            or "third_person"
        )
        if mode not in VERTICAL_MODES:
            mode = "third_person"

        # Query all existing render jobs for this video to ensure idempotency
        already_staged_ids: set[str] = set()
        jobs = db.query(RenderJob).filter(RenderJob.video_id == video_id).all()
        for j in jobs:
            if j.highlight_candidate_id:
                already_staged_ids.add(j.highlight_candidate_id)
            elif j.clip_id and j.clip_id.startswith("auto_cand_"):
                already_staged_ids.add(j.clip_id[5:])

        candidates_to_stage: list[HighlightCandidate] = []
        skipped_ids: list[str] = []

        if candidate_ids:
            # Explicit selection mode
            cands = (
                db.query(HighlightCandidate)
                .filter(
                    HighlightCandidate.video_id == video_id,
                    HighlightCandidate.id.in_(candidate_ids),
                )
                .order_by(HighlightCandidate.score.desc())
                .all()
            )
            cand_map = {c.id: c for c in cands}
            for cid in candidate_ids:
                if cid in already_staged_ids:
                    skipped_ids.append(cid)
                elif cid in cand_map:
                    candidates_to_stage.append(cand_map[cid])
        else:
            # Top N Left mode
            count = max(
                0, int(top_n if top_n is not None else settings.AUTO_STAGE_TOP_N)
            )
            threshold = float(
                min_score if min_score is not None else settings.AUTO_STAGE_MIN_SCORE
            )
            candidates = (
                db.query(HighlightCandidate)
                .filter(
                    HighlightCandidate.video_id == video_id,
                    HighlightCandidate.score >= threshold,
                )
                .order_by(
                    HighlightCandidate.score.desc(), HighlightCandidate.start_seconds
                )
                .all()
            )
            for c in candidates:
                if c.id in already_staged_ids:
                    skipped_ids.append(c.id)
                elif len(candidates_to_stage) < count:
                    candidates_to_stage.append(c)

        if not candidates_to_stage:
            return {
                "video_id": video_id,
                "requested_count": len(candidate_ids)
                if candidate_ids
                else (top_n or 0),
                "staged_count": 0,
                "skipped_count": len(skipped_ids),
                "staged_clips": [],
                "skipped_candidate_ids": skipped_ids,
                "message": "No eligible unprocessed candidates found to stage.",
            }

        slots: list[datetime] = []
        if schedule:
            slots = cls.compute_batch_publish_slots(
                db,
                count=len(candidates_to_stage),
                same_day_catchup=same_day_catchup,
            )

        staged: list[dict[str, Any]] = []
        for idx, candidate in enumerate(candidates_to_stage):
            assigned_slot = slots[idx] if idx < len(slots) else None
            try:
                summary = cls._stage_candidate(
                    db,
                    video=video,
                    candidate=candidate,
                    mode=mode,
                    slot=assigned_slot,
                    background_tasks=background_tasks,
                )
                staged.append(summary)
            except Exception as exc:
                logger.warning(
                    "Batch stage failed for candidate %s: %s", candidate.id, exc
                )
                db.rollback()
                continue

        return {
            "video_id": video_id,
            "requested_count": len(candidate_ids) if candidate_ids else (top_n or 0),
            "staged_count": len(staged),
            "skipped_count": len(skipped_ids),
            "staged_clips": staged,
            "skipped_candidate_ids": skipped_ids,
            "message": f"Successfully staged {len(staged)} highlight clip(s) as {mode}.",
        }

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
        profile = ChannelProfileService.get_or_create(db)
        mode = (
            clipping_mode
            or profile.default_framing_preset
            or settings.AUTO_STAGE_CLIPPING_MODE
            or "third_person"
        )
        if mode not in VERTICAL_MODES:
            mode = "third_person"

        if count == 0:
            return {
                "video_id": video_id,
                "staged_count": 0,
                "clips": [],
                "message": "Auto-stage disabled (top_n=0).",
            }

        already_staged_subquery = db.query(RenderJob.highlight_candidate_id).filter(
            RenderJob.highlight_candidate_id.isnot(None)
        )
        candidates = (
            db.query(HighlightCandidate)
            .filter(
                HighlightCandidate.video_id == video_id,
                HighlightCandidate.score >= threshold,
                ~HighlightCandidate.id.in_(already_staged_subquery),
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
        booked_slots: set[datetime] = set()
        if schedule:
            existing_scheduled = (
                db.query(RenderJob.scheduled_publish_at)
                .filter(RenderJob.scheduled_publish_at.isnot(None))
                .all()
            )
            for row in existing_scheduled:
                u = as_utc(row[0])
                if u:
                    booked_slots.add(u)

        slot = (
            cls.next_publish_slot(db, booked_slots=booked_slots) if schedule else None
        )

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
                booked_slots.add(slot)
                slot = cls.next_publish_slot(db, after=slot, booked_slots=booked_slots)

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
    def stage_all_top_candidates(
        cls,
        db: Session,
        *,
        top_n: int | None = None,
        min_score: float | None = None,
        clipping_mode: str | None = None,
        schedule: bool = True,
        background_tasks: Any = None,
    ) -> dict[str, Any]:
        """Stage top candidates across every downloaded video.

        Candidates are grouped per video and staged in batches of ``top_n``
        (``AUTO_STAGE_TOP_N`` by default), highest-scoring video first. Already
        staged candidates are excluded, so repeated sweeps keep consuming the
        next-best highlights until a video runs out.
        """
        count = max(0, int(top_n if top_n is not None else settings.AUTO_STAGE_TOP_N))
        threshold = float(
            min_score if min_score is not None else settings.AUTO_STAGE_MIN_SCORE
        )

        if count == 0:
            return {
                "videos_processed": 0,
                "staged_count": 0,
                "clips": [],
                "message": "Auto-stage disabled (top_n=0).",
            }

        staged_subquery = db.query(RenderJob.highlight_candidate_id).filter(
            RenderJob.highlight_candidate_id.isnot(None)
        )
        video_rows = (
            db.query(
                HighlightCandidate.video_id,
                func.max(HighlightCandidate.score).label("top_score"),
            )
            .join(Video, Video.id == HighlightCandidate.video_id)
            .filter(
                HighlightCandidate.score >= threshold,
                ~HighlightCandidate.id.in_(staged_subquery),
                Video.is_downloaded.is_(True),
            )
            .group_by(HighlightCandidate.video_id)
            .order_by(func.max(HighlightCandidate.score).desc())
            .all()
        )

        total_staged = 0
        clips: list[dict[str, Any]] = []
        videos_with_staged = 0

        for video_id, _ in video_rows:
            try:
                result = cls.stage_top_candidates(
                    db,
                    video_id,
                    top_n=count,
                    min_score=threshold,
                    clipping_mode=clipping_mode,
                    schedule=schedule,
                    background_tasks=background_tasks,
                )
            except Exception as exc:
                logger.warning("Bulk auto-stage failed for video %s: %s", video_id, exc)
                db.rollback()
                continue

            staged_count = int(result.get("staged_count", 0) or 0)
            if staged_count:
                videos_with_staged += 1
                total_staged += staged_count
                clips.extend(result.get("clips", []))

        message = (
            f"Auto-staged {total_staged} clip(s) across "
            f"{videos_with_staged} video(s) in batches of {count}."
            if total_staged
            else "No candidates met the auto-stage criteria."
        )
        logger.info("Bulk auto-stage: %s", message)
        return {
            "videos_processed": len(video_rows),
            "staged_count": total_staged,
            "clips": clips,
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
        existing_job = db.query(RenderJob).filter(RenderJob.clip_id == clip_id).first()
        if existing_job:
            raise RuntimeError("clip already exists")

        budget = ChannelProfileService.duration_budget(db)
        candidate_duration = float(candidate.duration_seconds or 15.0)
        duration = max(3.0, min(budget.clip_budget, candidate_duration))
        if candidate_duration > budget.clip_budget:
            logger.info(
                "Candidate %s trimmed %.1fs -> %.1fs so the branded clip fits "
                "the %.0fs ceiling (%.1fs of cards)",
                candidate.id,
                candidate_duration,
                duration,
                budget.max_seconds,
                budget.bookend_seconds,
            )
        request = RenderClipRequest(
            video_id=video.id,
            start_seconds=float(candidate.start_seconds),
            duration_seconds=duration,
            clip_id=clip_id,
            crop_preset=(
                mode
                if mode in ("third_person", "direct_crop", "cinematic", "custom")
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
            is_short=budget.is_uploadable(duration),
        )
        profile = ChannelProfileService.get_or_create(db)
        if profile.title_template:
            metadata["title"] = apply_title_template(
                profile.title_template,
                metadata.get("title") or "",
                channel_name=profile.channel_name,
                hero_name=metadata.get("hero_name"),
                game=metadata.get("game"),
                event_type=getattr(candidate, "event_type", None),
                clip_id=clip_id,
            )
        privacy = (
            "private"
            if slot is not None
            else (profile.default_privacy or metadata.get("privacy") or "public")
        )
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
                hero_name=metadata.get("hero_name"),
                clip_context=metadata.get("clip_context"),
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
        if metadata.get("hero_name"):
            staged_meta["hero_name"] = metadata["hero_name"]
        if metadata.get("clip_context"):
            staged_meta["clip_context"] = metadata["clip_context"]
        if metadata.get("game"):
            staged_meta["game"] = metadata["game"]
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
