"""add clip length ceiling to channel profiles

Revision ID: c7f1a9d3e5b2
Revises: b4d8e2f6a1c3
Create Date: 2026-10-31 00:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c7f1a9d3e5b2"
down_revision: str | None = "b4d8e2f6a1c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "channel_profiles" not in inspector.get_table_names():
        return

    existing = {column["name"] for column in inspector.get_columns("channel_profiles")}
    if "max_clip_seconds" in existing:
        return
    # Nullable on purpose: rows created before the ceiling existed fall back to
    # settings.MAX_CLIP_SECONDS instead of silently restricting renders.
    op.add_column(
        "channel_profiles",
        sa.Column("max_clip_seconds", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "channel_profiles" not in inspector.get_table_names():
        return

    existing = {column["name"] for column in inspector.get_columns("channel_profiles")}
    if "max_clip_seconds" in existing:
        op.drop_column("channel_profiles", "max_clip_seconds")
