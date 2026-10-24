"""add auto-stage scheduling and youtube quota usage

Revision ID: c4f8a1d27b90
Revises: 7548b2f4b6a5
Create Date: 2026-10-24 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4f8a1d27b90"
down_revision: str | None = "7548b2f4b6a5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "render_jobs",
        sa.Column("auto_staged", sa.Boolean(), nullable=True, server_default=sa.false()),
    )
    op.add_column(
        "render_jobs",
        sa.Column("highlight_candidate_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "render_jobs",
        sa.Column("scheduled_publish_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_render_jobs_auto_staged", "render_jobs", ["auto_staged"], unique=False
    )
    op.create_index(
        "ix_render_jobs_highlight_candidate_id",
        "render_jobs",
        ["highlight_candidate_id"],
        unique=False,
    )
    op.create_index(
        "ix_render_jobs_scheduled_publish_at",
        "render_jobs",
        ["scheduled_publish_at"],
        unique=False,
    )

    op.create_table(
        "youtube_quota_usage",
        sa.Column("day", sa.String(length=10), nullable=False),
        sa.Column("units_used", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("uploads_count", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("day"),
    )
    op.create_index(
        "ix_youtube_quota_usage_day",
        "youtube_quota_usage",
        ["day"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_youtube_quota_usage_day", table_name="youtube_quota_usage")
    op.drop_table("youtube_quota_usage")

    op.drop_index("ix_render_jobs_scheduled_publish_at", table_name="render_jobs")
    op.drop_index("ix_render_jobs_highlight_candidate_id", table_name="render_jobs")
    op.drop_index("ix_render_jobs_auto_staged", table_name="render_jobs")
    op.drop_column("render_jobs", "scheduled_publish_at")
    op.drop_column("render_jobs", "highlight_candidate_id")
    op.drop_column("render_jobs", "auto_staged")
