"""YouTubeQuotaUsage SQLAlchemy model for daily Data API quota accounting."""

from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, Integer, String

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
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    def to_dict(self) -> dict:
        return {
            "day": self.day,
            "units_used": self.units_used or 0,
            "uploads_count": self.uploads_count or 0,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
