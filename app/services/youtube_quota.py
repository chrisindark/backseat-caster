"""YouTube Data API quota accounting.

YouTube resets the 10,000 unit daily quota at midnight Pacific time. An upload
costs 1,600 units, so a fresh project budget supports six uploads. Consumption
is recorded only after YouTube accepts an upload, so rejected requests do not
inflate the local counter.

YouTube can also reject uploads with ``uploadLimitExceeded``: the channel's own
video upload limit, which is unrelated to the Data API unit budget. Both kinds
of rejection are persisted as a block so the UI can explain the real cause and
show when a retry makes sense.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from app.config import settings
from app.models.youtube_quota import YouTubeQuotaUsage
from app.services.youtube_errors import YouTubeUploadError

logger = logging.getLogger(__name__)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class YouTubeQuotaService:
    """Track the YouTube Data API daily unit budget (advisory, non-blocking)."""

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
        moment = _as_utc(now) or datetime.now(UTC)
        return moment.astimezone(tz).date().isoformat()

    @classmethod
    def resets_at(cls, now: datetime | None = None) -> datetime:
        """Return the next quota reset instant (midnight Pacific) in UTC."""
        tz = cls._timezone()
        moment = _as_utc(now) or datetime.now(UTC)
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
                day=target_day, units_used=0, uploads_count=0, failed_uploads=0
            )
            db.add(usage)
            db.commit()
            db.refresh(usage)
        return usage

    @classmethod
    def get_summary(cls, db: Session, now: datetime | None = None) -> dict[str, Any]:
        """Return quota consumption plus the active API/channel block state."""
        current = _as_utc(now) or datetime.now(UTC)
        daily_limit = max(1, int(settings.YOUTUBE_DAILY_QUOTA_UNITS))
        upload_cost = max(1, int(settings.YOUTUBE_UPLOAD_QUOTA_COST))
        usage = cls.get_or_create_usage(db, cls.quota_day(current))
        units_used = int(usage.units_used or 0)
        units_remaining = max(0, daily_limit - units_used)
        max_uploads = daily_limit // upload_cost
        uploads_remaining = units_remaining // upload_cost
        blocked_until = _as_utc(usage.blocked_until)
        blocked_active = blocked_until is not None and blocked_until > current
        blocked_reason = usage.blocked_reason if blocked_active else None
        return {
            "quota_day": usage.day,
            "daily_limit_units": daily_limit,
            "units_used": units_used,
            "units_remaining": units_remaining,
            "upload_quota_cost": upload_cost,
            "max_uploads_per_day": max_uploads,
            "uploads_today": int(usage.uploads_count or 0),
            "uploads_remaining": uploads_remaining,
            "failed_uploads": int(usage.failed_uploads or 0),
            "can_upload": uploads_remaining > 0 and not blocked_active,
            "blocked_reason": blocked_reason,
            "blocked_until": blocked_until.isoformat() if blocked_active else None,
            "api_quota_exhausted": units_remaining < upload_cost
            or blocked_reason == "api_quota_exceeded",
            "upload_limit_exceeded": blocked_reason == "upload_limit_exceeded",
            "last_error_code": usage.last_error_code,
            "last_error_message": usage.last_error_message,
            "last_error_at": usage.last_error_at.isoformat()
            if usage.last_error_at
            else None,
            "resets_at": cls.resets_at(current).isoformat(),
        }

    @classmethod
    def record_upload_success(
        cls, db: Session, units: int | None = None
    ) -> dict[str, Any]:
        """Charge one successful upload against today's API budget."""
        cost = int(units or settings.YOUTUBE_UPLOAD_QUOTA_COST)
        summary = cls.get_summary(db)
        usage = cls.get_or_create_usage(db, summary["quota_day"])
        usage.units_used = int(usage.units_used or 0) + cost
        usage.uploads_count = int(usage.uploads_count or 0) + 1
        # A successful upload means the account can upload again; clear any
        # stale block from an earlier rejection in this quota day.
        usage.blocked_reason = None
        usage.blocked_until = None
        db.commit()
        db.refresh(usage)
        logger.info(
            "Recorded %d YouTube quota units for a successful upload "
            "(day %s: %d/%d units used)",
            cost,
            usage.day,
            usage.units_used,
            int(settings.YOUTUBE_DAILY_QUOTA_UNITS),
        )
        return cls.get_summary(db)

    @classmethod
    def record_upload_failure(
        cls, db: Session, error: YouTubeUploadError
    ) -> dict[str, Any]:
        """Persist a failed upload and any YouTube-imposed block state."""
        now = datetime.now(UTC)
        usage = cls.get_or_create_usage(db, cls.quota_day(now))
        usage.failed_uploads = int(usage.failed_uploads or 0) + 1
        usage.last_error_code = error.error_code
        usage.last_error_message = error.user_message
        usage.last_error_at = now

        retry_at = _as_utc(error.retry_at) or cls.resets_at(now)
        if error.api_quota_exhausted:
            # YouTube says the project has no quota left. Reflect that in the
            # bar even if our own successful-upload estimate was lower.
            usage.units_used = max(
                int(usage.units_used or 0),
                int(settings.YOUTUBE_DAILY_QUOTA_UNITS),
            )
            usage.blocked_reason = "api_quota_exceeded"
            usage.blocked_until = retry_at
        elif error.upload_limit_exceeded:
            usage.blocked_reason = "upload_limit_exceeded"
            usage.blocked_until = retry_at

        db.commit()
        db.refresh(usage)
        logger.warning(
            "Recorded YouTube upload failure (%s) on quota day %s; blocked=%s until %s",
            error.error_code,
            usage.day,
            usage.blocked_reason,
            usage.blocked_until,
        )
        return cls.get_summary(db)

    # Backwards-compatible alias used by older callers/tests.
    @classmethod
    def reserve_upload(cls, db: Session, units: int | None = None) -> dict[str, Any]:
        return cls.record_upload_success(db, units)
