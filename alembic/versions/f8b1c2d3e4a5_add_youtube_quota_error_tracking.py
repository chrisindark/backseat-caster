"""add youtube quota error and block tracking

Revision ID: f8b1c2d3e4a5
Revises: e1a2b3c4d5e6
Create Date: 2026-10-30 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f8b1c2d3e4a5"
down_revision: str | Sequence[str] | None = "e1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Record failed upload attempts and explicit YouTube block state."""
    op.add_column(
        "youtube_quota_usage",
        sa.Column("failed_uploads", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "youtube_quota_usage",
        sa.Column("blocked_reason", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "youtube_quota_usage",
        sa.Column("blocked_until", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "youtube_quota_usage",
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "youtube_quota_usage",
        sa.Column("last_error_message", sa.Text(), nullable=True),
    )
    op.add_column(
        "youtube_quota_usage",
        sa.Column("last_error_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    """Remove YouTube quota error tracking columns."""
    op.drop_column("youtube_quota_usage", "last_error_at")
    op.drop_column("youtube_quota_usage", "last_error_message")
    op.drop_column("youtube_quota_usage", "last_error_code")
    op.drop_column("youtube_quota_usage", "blocked_until")
    op.drop_column("youtube_quota_usage", "blocked_reason")
    op.drop_column("youtube_quota_usage", "failed_uploads")
