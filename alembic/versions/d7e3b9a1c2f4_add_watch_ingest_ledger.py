"""add watch ingest ledger for zero-click OBS ingestion

Revision ID: d7e3b9a1c2f4
Revises: c4f8a1d27b90
Create Date: 2026-10-30 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d7e3b9a1c2f4"
down_revision: str | None = "c4f8a1d27b90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "watch_ingests",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("source_path", sa.String(length=1024), nullable=False),
        sa.Column("source_name", sa.String(length=512), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("file_mtime", sa.Float(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="discovered",
        ),
        sa.Column("video_id", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_path", name="uq_watch_ingests_source_path"),
    )
    op.create_index("ix_watch_ingests_id", "watch_ingests", ["id"], unique=False)
    op.create_index(
        "ix_watch_ingests_source_path",
        "watch_ingests",
        ["source_path"],
        unique=False,
    )
    op.create_index(
        "ix_watch_ingests_status", "watch_ingests", ["status"], unique=False
    )
    op.create_index(
        "ix_watch_ingests_video_id", "watch_ingests", ["video_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_watch_ingests_video_id", table_name="watch_ingests")
    op.drop_index("ix_watch_ingests_status", table_name="watch_ingests")
    op.drop_index("ix_watch_ingests_source_path", table_name="watch_ingests")
    op.drop_index("ix_watch_ingests_id", table_name="watch_ingests")
    op.drop_table("watch_ingests")
