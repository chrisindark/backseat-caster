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
                day=target_day,
                units_used=0,
                upload_units_used=0,
                analytics_units_used=0,
                uploads_count=0,
                failed_uploads=0,
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
        upload_units_used = int(getattr(usage, "upload_units_used", 0) or 0)
        analytics_units_used = int(getattr(usage, "analytics_units_used", 0) or 0)
        upload_budget = max(
            upload_cost, int(getattr(settings, "YOUTUBE_UPLOAD_QUOTA_UNITS", 8000) or 8000)
        )
        analytics_budget = max(
            1,
            int(getattr(settings, "YOUTUBE_ANALYTICS_QUOTA_UNITS", 2000) or 2000),
        )
        max_uploads = daily_limit // upload_cost
        uploads_remaining = max(0, (upload_budget - upload_units_used) // upload_cost)
        analytics_remaining = max(0, analytics_budget - analytics_units_used)
        blocked_until = _as_utc(usage.blocked_until)
        blocked_active = blocked_until is not None and blocked_until > current
        blocked_reason = usage.blocked_reason if blocked_active else None
        usage_fraction = units_used / daily_limit
        threshold = float(settings.YOUTUBE_ANALYTICS_QUOTA_THRESHOLD)
        # Separate gates: uploads consult the upload budget, analytics the
        # analytics budget. Only an explicit API-quota block stops polls;
        # the channel upload limit never blocks analytics reads.
        api_blocked = blocked_active and blocked_reason == "api_quota_exceeded"
        analytics_allowed = not api_blocked and analytics_remaining > 0
        upload_allowed = not blocked_active and uploads_remaining > 0
        return {
            "quota_day": usage.day,
            "daily_limit_units": daily_limit,
            "units_used": units_used,
            "units_remaining": units_remaining,
            "upload_quota_cost": upload_cost,
            "upload_budget_units": upload_budget,
            "analytics_budget_units": analytics_budget,
            "upload_units_used": upload_units_used,
            "analytics_units_used": analytics_units_used,
            "analytics_units_remaining": analytics_remaining,
            "upload_units_remaining": max(0, upload_budget - upload_units_used),
            "max_uploads_per_day": max_uploads,
            "uploads_today": int(usage.uploads_count or 0),
            "uploads_remaining": uploads_remaining,
            "failed_uploads": int(usage.failed_uploads or 0),
            "can_upload": upload_allowed,
            "can_analytics": analytics_allowed,
            "analytics_blocked": not analytics_allowed,
            "usage_fraction": round(usage_fraction, 4),
            "analytics_threshold": threshold,
            "analytics_batch_limit": int(settings.YOUTUBE_ANALYTICS_BATCH_LIMIT),
            "backoff_max_attempts": int(settings.YOUTUBE_BACKOFF_MAX_ATTEMPTS),
            "backoff_base_seconds": float(settings.YOUTUBE_BACKOFF_BASE_SECONDS),
            "blocked_reason": blocked_reason,
            "blocked_until": blocked_until.isoformat() if blocked_active else None,
            "api_quota_exhausted": (uploads_remaining <= 0 and analytics_remaining <= 0)
            or blocked_reason == "api_quota_exceeded",
            "upload_budget_exhausted": uploads_remaining <= 0,
            "analytics_budget_exhausted": analytics_remaining <= 0,
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
        try:
            usage.upload_units_used = int(getattr(usage, "upload_units_used", 0) or 0) + cost
        except Exception:
            pass
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
    def record_units_used(
        cls, db: Session, units: int, kind: str = "analytics"
    ) -> dict[str, Any]:
        """Record arbitrary units consumed (e.g. 1 unit for statistics polling).

        ``kind`` routes the charge to the separate analytics or upload
        counter; both still count toward the shared daily total.
        """
        if units <= 0:
            return cls.get_summary(db)
        summary = cls.get_summary(db)
        usage = cls.get_or_create_usage(db, summary["quota_day"])
        usage.units_used = int(usage.units_used or 0) + units
        try:
            if kind == "upload":
                usage.upload_units_used = int(getattr(usage, "upload_units_used", 0) or 0) + units
            else:
                usage.analytics_units_used = int(getattr(usage, "analytics_units_used", 0) or 0) + units
        except Exception:
            pass
        db.commit()
        db.refresh(usage)
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
            try:
                usage.upload_units_used = max(
                    int(getattr(usage, "upload_units_used", 0) or 0),
                    int(getattr(settings, "YOUTUBE_UPLOAD_QUOTA_UNITS", 8000) or 8000),
                )
                usage.analytics_units_used = max(
                    int(getattr(usage, "analytics_units_used", 0) or 0),
                    int(getattr(settings, "YOUTUBE_ANALYTICS_QUOTA_UNITS", 2000) or 2000),
                )
            except Exception:
                pass
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

    @classmethod
    def check_analytics_budget(
        cls, db: Session, units_needed: int = 1, now: datetime | None = None
    ) -> dict[str, Any]:
        """Gate analytics polling on the *analytics* unit budget.

        Independent from the upload budget: exhausting uploads (even at
        9,600/10,000 total) does not block analytics until the analytics
        budget (default 2,000 units) is spent.
        """
        summary = cls.get_summary(db, now=now)
        reason: str | None = None
        if summary["blocked_reason"] == "api_quota_exceeded":
            reason = "api_quota_exhausted"
        if summary["analytics_units_remaining"] < units_needed:
            reason = "analytics_budget_exceeded"
        elif summary["units_remaining"] < units_needed:
            reason = "api_quota_exhausted"
        summary["can_analytics"] = reason is None
        summary["analytics_blocked"] = reason is not None
        summary["analytics_block_reason"] = reason
        return summary

    @classmethod
    def check_upload_budget(cls, db: Session, now: datetime | None = None) -> dict[str, Any]:
        """Pre-flight gate for a single upload (advisory, non-raising).

        Considers only the upload unit budget (default 8,000); analytics
        consumption never blocks uploads and vice versa.
        """
        summary = cls.get_summary(db, now=now)
        reason: str | None = None
        if summary["blocked_reason"] == "api_quota_exceeded":
            reason = "api_quota_exceeded"
        elif summary["blocked_reason"] == "upload_limit_exceeded":
            reason = "upload_limit_exceeded"
        elif (
            summary["uploads_remaining"] <= 0
            or summary["upload_units_remaining"] < summary["upload_quota_cost"]
        ):
            reason = "insufficient_quota_units"
        summary["upload_block_reason"] = reason
        return summary

    @classmethod
    def backoff_sleep(cls, attempt: int) -> float:
        """Sleep with exponential backoff for a failed attempt number."""
        import time

        delay = min(
            float(settings.YOUTUBE_BACKOFF_MAX_SECONDS),
            float(settings.YOUTUBE_BACKOFF_BASE_SECONDS) * (2.0**attempt),
        )
        logger.warning("YouTube quota throttle: backing off %.1fs (attempt %d)", delay, attempt + 1)
        time.sleep(delay)
        return delay
