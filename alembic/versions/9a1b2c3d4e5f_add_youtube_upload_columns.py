"""add youtube upload columns to render_jobs

Revision ID: 9a1b2c3d4e5f
Revises: 86c5d2b7b10a
Create Date: 2026-10-13 03:50:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9a1b2c3d4e5f"
down_revision: str | Sequence[str] | None = "86c5d2b7b10a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema with YouTube upload tracking columns."""
    op.add_column(
        "render_jobs",
        sa.Column("youtube_video_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "render_jobs",
        sa.Column(
            "youtube_upload_status",
            sa.String(length=32),
            server_default="not_uploaded",
            nullable=True,
        ),
    )
    op.add_column(
        "render_jobs",
        sa.Column(
            "youtube_upload_progress", sa.Float(), server_default="0.0", nullable=True
        ),
    )
    op.add_column(
        "render_jobs",
        sa.Column("youtube_upload_url", sa.String(length=256), nullable=True),
    )
    op.add_column(
        "render_jobs", sa.Column("youtube_uploaded_at", sa.DateTime(), nullable=True)
    )
    op.add_column(
        "render_jobs", sa.Column("youtube_upload_error", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("render_jobs", "youtube_upload_error")
    op.drop_column("render_jobs", "youtube_uploaded_at")
    op.drop_column("render_jobs", "youtube_upload_url")
    op.drop_column("render_jobs", "youtube_upload_progress")
    op.drop_column("render_jobs", "youtube_upload_status")
    op.drop_column("render_jobs", "youtube_video_id")
