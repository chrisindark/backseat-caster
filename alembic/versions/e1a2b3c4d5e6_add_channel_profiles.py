"""add channel brand profiles and render quality preset

Revision ID: e1a2b3c4d5e6
Revises: d7e3b9a1c2f4
Create Date: 2026-10-30 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e1a2b3c4d5e6"
down_revision: str | None = "d7e3b9a1c2f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "channel_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("channel_name", sa.String(length=255), nullable=True),
        sa.Column("watermark_path", sa.String(length=1024), nullable=True),
        sa.Column("watermark_enabled", sa.Boolean(), nullable=True, server_default="0"),
        sa.Column(
            "watermark_position",
            sa.String(length=32),
            nullable=True,
            server_default="bottom_right",
        ),
        sa.Column(
            "watermark_opacity", sa.Float(), nullable=True, server_default="0.85"
        ),
        sa.Column("watermark_scale", sa.Float(), nullable=True, server_default="0.14"),
        sa.Column("watermark_margin", sa.Float(), nullable=True, server_default="0.03"),
        sa.Column(
            "default_framing_preset",
            sa.String(length=64),
            nullable=True,
            server_default="third_person",
        ),
        sa.Column(
            "default_quality_preset",
            sa.String(length=32),
            nullable=True,
            server_default="high",
        ),
        sa.Column("title_template", sa.String(length=255), nullable=True),
        sa.Column("pinned_hashtags", sa.Text(), nullable=True),
        sa.Column(
            "default_privacy",
            sa.String(length=32),
            nullable=True,
            server_default="public",
        ),
        sa.Column("upload_slots", sa.Text(), nullable=True),
        sa.Column(
            "upload_timezone",
            sa.String(length=64),
            nullable=True,
            server_default="UTC",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.add_column(
        "render_jobs",
        sa.Column("quality_preset", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("render_jobs", "quality_preset")
    op.drop_table("channel_profiles")
