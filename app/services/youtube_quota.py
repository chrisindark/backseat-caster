"""YouTube Data API quota accounting.

YouTube resets the 10,000 unit daily quota at midnight Pacific time. Uploads
cost 1,600 units, so a fresh day supports six uploads. This service records
consumption per quota day and guards auto-publish dispatch before it burns
units that are not available.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from app.config import settings
from app.models.youtube_quota import YouTubeQuotaUsage

logger = logging.getLogger(__name__)


class QuotaExceededError(RuntimeError):
    """Raised when a YouTube upload cannot be dispatched within daily quota."""


class YouTubeQuotaService:
    """Track and guard the YouTube Data API daily unit budget."""

    @staticmethod
    def _timezone() -> ZoneInfo:
        try:
            return ZoneInfo(settings.YOUTUBE_QUOTA_TIMEZONE)
        except (ZoneInfoNotFoundError, ValueError):
            logger.warning(
                "Unknown YOUTUBE_QUOTA_TIMEZONE '%s'; falling back to UTC",
                settings.YOUTUBE_QUOTA_TIMEZONE,
            )
            return ZoneInfo("UTC")

    @classmethod
    def quota_day(cls, now: datetime | None = None) -> str:
        """Return the YYYY-MM-DD quota day in the configured Pacific timezone."""
        tz = cls._timezone()
        moment = now or datetime.now(UTC)
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=UTC)
        return moment.astimezone(tz).date().isoformat()

    @classmethod
    def resets_at(cls, now: datetime | None = None) -> datetime:
        """Return the next quota reset instant (midnight Pacific) in UTC."""
        tz = cls._timezone()
        moment = now or datetime.now(UTC)
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=UTC)
        local = moment.astimezone(tz)
        next_midnight = datetime.combine(
            local.date() + timedelta(days=1), time.min, tzinfo=tz
        )
        return next_midnight.astimezone(UTC)

    @classmethod
    def get_or_create_usage(
        cls, db: Session, day: str | None = None
    ) -> YouTubeQuotaUsage:
        target_day = day or cls.quota_day()
        usage = db.query(YouTubeQuotaUsage).filter_by(day=target_day).first()
        if usage is None:
            usage = YouTubeQuotaUsage(
                day=target_day, units_used=0, uploads_count=0
            )
            db.add(usage)
            db.commit()
            db.refresh(usage)
        return usage

    @classmethod
    def get_summary(cls, db: Session, now: datetime | None = None) -> dict[str, Any]:
        """Return quota consumption plus remaining upload capacity."""
        daily_limit = int(settings.YOUTUBE_DAILY_QUOTA_UNITS)
        upload_cost = max(1, int(settings.YOUTUBE_UPLOAD_QUOTA_COST))
        usage = cls.get_or_create_usage(db, cls.quota_day(now))
        units_used = int(usage.units_used or 0)
        units_remaining = max(0, daily_limit - units_used)
        max_uploads = daily_limit // upload_cost
        uploads_remaining = units_remaining // upload_cost
        return {
            "quota_day": usage.day,
            "daily_limit_units": daily_limit,
            "units_used": units_used,
            "units_remaining": units_remaining,
            "upload_quota_cost": upload_cost,
            "max_uploads_per_day": max_uploads,
            "uploads_today": int(usage.uploads_count or 0),
            "uploads_remaining": uploads_remaining,
            "can_upload": uploads_remaining > 0,
            "resets_at": cls.resets_at(now).isoformat(),
        }

    @classmethod
    def ensure_capacity(cls, db: Session, uploads: int = 1) -> None:
        """Raise :class:`QuotaExceededError` when the remaining budget is short."""
        summary = cls.get_summary(db)
        if summary["uploads_remaining"] < uploads:
            raise QuotaExceededError(
                "YouTube daily API quota exhausted: "
                f"{summary['uploads_remaining']} of {uploads} requested upload(s) "
                f"available today. Quota resets at {summary['resets_at']}."
            )

    @classmethod
    def reserve_upload(cls, db: Session, units: int | None = None) -> dict[str, Any]:
        """Consume one upload's worth of quota and return the fresh summary."""
        cost = int(units or settings.YOUTUBE_UPLOAD_QUOTA_COST)
        summary = cls.get_summary(db)
        if summary["units_remaining"] < cost:
            raise QuotaExceededError(
                "YouTube daily API quota exhausted: "
                f"{summary['units_remaining']} unit(s) remaining, "
                f"{cost} required per upload. Quota resets at {summary['resets_at']}."
            )
        usage = cls.get_or_create_usage(db, summary["quota_day"])
        usage.units_used = int(usage.units_used or 0) + cost
        usage.uploads_count = int(usage.uploads_count or 0) + 1
        db.commit()
        db.refresh(usage)
        logger.info(
            "Reserved %d YouTube quota units for upload (day %s: %d/%d units used)",
            cost,
            usage.day,
            usage.units_used,
            int(settings.YOUTUBE_DAILY_QUOTA_UNITS),
        )
        return cls.get_summary(db)
