"""Zero-input auto-mine: chain a completed ingest straight into highlight mining.

Tier 2 of the adoption roadmap. Without this, a creator has to click through
"download → open video → run highlight scan → batch stage" for every VOD. With
``AUTO_MINE_ON_INGEST`` enabled, a finished download or OBS upload dispatches the
existing Phase 2/3 detection pipeline automatically, which in turn auto-stages
the top candidates (Phase 8) and schedules them with native ``publishAt``.

The service deliberately delegates to ``HighlightService.detect_highlights`` so
run records, status transitions, detector resolution, Celery dispatch and the
``BackgroundTasks`` fallback all stay in one place.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.models.video import Video

logger = logging.getLogger(__name__)

# Highlight states that mean "already handled"; auto-mine must not re-scan them.
_ALREADY_MINED_STATES = {"completed", "scanning", "pending"}


class AutoMineService:
    """Resolve whether a freshly ingested video should be mined, and dispatch it."""

    @staticmethod
    def is_enabled() -> bool:
        """Whether the auto-mine-on-ingest pipeline is switched on."""
        return bool(settings.AUTO_MINE_ON_INGEST)

    @classmethod
    def resolve_top_n(cls) -> int:
        """How many candidates to auto-render once mining finishes."""
        return settings.auto_mine_top_n

    @classmethod
    def resolve_game(cls, video: Video) -> str | None:
        """Pick an explicit detector profile, or fall back to metadata detection.

        An explicit ``AUTO_MINE_GAME`` always wins so a creator running a single
        game can pin the profile. Otherwise ``None`` lets the detector registry
        auto-detect from the title/description instead of silently defaulting to
        a generic profile here.
        """
        configured = (settings.AUTO_MINE_GAME or "").strip()
        if configured:
            return configured
        return None

    @classmethod
    def should_mine(cls, video: Video | None) -> tuple[bool, str]:
        """Return (should_mine, reason) for a video that just finished ingesting."""
        if not cls.is_enabled():
            return False, "auto-mine disabled"
        if video is None:
            return False, "video not found"
        if not video.is_downloaded or video.download_status != "completed":
            return False, "video is not locally available"
        if video.highlight_status in _ALREADY_MINED_STATES:
            return False, f"highlight status already '{video.highlight_status}'"
        if not video.local_file_path:
            return False, "no local file path recorded"
        if not Path(video.local_file_path).exists():
            return False, f"local file missing at {video.local_file_path}"
        return True, "ready"

    @classmethod
    def trigger_after_ingest(
        cls,
        db: Session,
        video_id: str,
        *,
        background_tasks: Any = None,
    ) -> dict[str, Any]:
        """Dispatch highlight mining for a freshly ingested video.

        Returns a small status dict instead of raising: a failed auto-mine must
        never break the download/upload that actually got the file onto disk.
        """
        try:
            video = db.query(Video).filter(Video.id == video_id).first()
            ok, reason = cls.should_mine(video)
            if not ok:
                logger.info("Auto-mine skipped for video %s: %s", video_id, reason)
                return {
                    "triggered": False,
                    "video_id": video_id,
                    "reason": reason,
                }

            # Imported lazily to avoid a circular import:
            # highlight.service -> renders -> videos -> auto_mine
            from app.schemas.highlight import DetectHighlightsRequest
            from app.services.highlight.service import HighlightService

            detect_request = DetectHighlightsRequest(
                game=cls.resolve_game(video),
                min_score=float(settings.AUTO_MINE_MIN_SCORE),
                auto_render_top_n=cls.resolve_top_n(),
                clipping_mode=settings.AUTO_STAGE_CLIPPING_MODE,
                force_rescan=False,
            )

            response = HighlightService.detect_highlights(
                db=db,
                video_id=video_id,
                request=detect_request,
                background_tasks=background_tasks,
            )

            logger.info(
                "Auto-mine dispatched for video %s (status=%s, top_n=%d, run=%s)",
                video_id,
                response.status,
                detect_request.auto_render_top_n or 0,
                response.run_id,
            )
            return {
                "triggered": True,
                "video_id": video_id,
                "status": response.status,
                "run_id": response.run_id,
                "task_id": response.task_id,
                "auto_render_top_n": detect_request.auto_render_top_n or 0,
            }

        except Exception as exc:  # never break an ingest that already succeeded
            logger.warning("Auto-mine could not start for video %s: %s", video_id, exc)
            try:
                db.rollback()
            except Exception:
                pass
            return {"triggered": False, "video_id": video_id, "reason": str(exc)}
