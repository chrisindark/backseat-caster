"""YouTubeQuotaUsage SQLAlchemy model for daily Data API quota accounting."""

from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from app.database import Base


def utc_now():
    return datetime.now(UTC)


class YouTubeQuotaUsage(Base):
    """Tracks YouTube Data API units consumed per quota day (Pacific time)."""

    __tablename__ = "youtube_quota_usage"

    # Quota day formatted as YYYY-MM-DD in the configured quota timezone.
    day = Column(String(10), primary_key=True, index=True)
    units_used = Column(Integer, default=0, nullable=False)
    uploads_count = Column(Integer, default=0, nullable=False)
    failed_uploads = Column(Integer, default=0, nullable=False)
    # Set only when YouTube has explicitly rejected uploads for the rest of the
    # quota day (api_quota_exceeded or upload_limit_exceeded).
    blocked_reason = Column(String(64), nullable=True)
    blocked_until = Column(DateTime, nullable=True)
    last_error_code = Column(String(64), nullable=True)
    last_error_message = Column(Text, nullable=True)
    last_error_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    def to_dict(self) -> dict:
        return {
            "day": self.day,
            "units_used": self.units_used or 0,
            "uploads_count": self.uploads_count or 0,
            "failed_uploads": self.failed_uploads or 0,
            "blocked_reason": self.blocked_reason,
            "blocked_until": self.blocked_until.isoformat()
            if self.blocked_until
            else None,
            "last_error_code": self.last_error_code,
            "last_error_message": self.last_error_message,
            "last_error_at": self.last_error_at.isoformat()
            if self.last_error_at
            else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
