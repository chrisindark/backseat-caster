"""add cinematic_treatment_enabled to channel profiles

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-11-01 02:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4d5e6f7a8b9"
down_revision: str | None = "b3c4d5e6f7a8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "channel_profiles" not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns("channel_profiles")}
    if "cinematic_treatment_enabled" not in existing:
        op.add_column(
            "channel_profiles",
            sa.Column("cinematic_treatment_enabled", sa.Boolean(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "channel_profiles" not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns("channel_profiles")}
    if "cinematic_treatment_enabled" in existing:
        op.drop_column("channel_profiles", "cinematic_treatment_enabled")
