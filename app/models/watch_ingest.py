"""Watch folder ingest ledger: dedupe records for zero-click OBS ingestion."""

from datetime import UTC, datetime

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Float,
    String,
    Text,
    UniqueConstraint,
)

from app.database import Base


class WatchIngest(Base):
    """One observed file in the watch folder and what happened to it.

    The ledger exists so repeated scans never re-ingest the same recording, while
    still picking the file up again if OBS overwrites it with a new take (which
    changes the size/mtime fingerprint).
    """

    __tablename__ = "watch_ingests"
    __table_args__ = (
        UniqueConstraint("source_path", name="uq_watch_ingests_source_path"),
    )

    id = Column(String(64), primary_key=True, index=True)
    source_path = Column(String(1024), nullable=False, index=True)
    source_name = Column(String(512), nullable=False)
    # "size:mtime" fingerprint used to detect a rewritten recording
    fingerprint = Column(String(64), nullable=False)
    file_size_bytes = Column(BigInteger, nullable=True)
    file_mtime = Column(Float, nullable=True)

    # discovered | ingested | failed | skipped
    status = Column(String(32), nullable=False, default="discovered", index=True)
    video_id = Column(String(64), nullable=True, index=True)
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    processed_at = Column(DateTime(timezone=True), nullable=True)

    def to_dict(self) -> dict:
        """Serialise the ingest ledger row."""
        return {
            "id": self.id,
            "source_path": self.source_path,
            "source_name": self.source_name,
            "fingerprint": self.fingerprint,
            "file_size_bytes": self.file_size_bytes,
            "file_mtime": self.file_mtime,
            "status": self.status,
            "video_id": self.video_id,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "processed_at": (
                self.processed_at.isoformat() if self.processed_at else None
            ),
        }
