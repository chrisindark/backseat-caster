"""add tracking_enabled to channel profiles

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-11-01 01:05:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b3c4d5e6f7a8"
down_revision: str | None = "a2b3c4d5e6f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "channel_profiles" not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns("channel_profiles")}
    if "tracking_enabled" not in existing:
        op.add_column(
            "channel_profiles",
            sa.Column("tracking_enabled", sa.Boolean(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "channel_profiles" not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns("channel_profiles")}
    if "tracking_enabled" in existing:
        op.drop_column("channel_profiles", "tracking_enabled")
