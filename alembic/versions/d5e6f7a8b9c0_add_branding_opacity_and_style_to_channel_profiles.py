"""add branding_opacity and branding_style to channel profiles

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-11-02 06:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d5e6f7a8b9c0"
down_revision: str | None = "c4d5e6f7a8b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "channel_profiles" not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns("channel_profiles")}
    if "branding_opacity" not in existing:
        op.add_column(
            "channel_profiles",
            sa.Column("branding_opacity", sa.Float(), nullable=True, server_default="0.85"),
        )
    if "branding_style" not in existing:
        op.add_column(
            "channel_profiles",
            sa.Column("branding_style", sa.String(32), nullable=True, server_default="bookend"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "channel_profiles" not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns("channel_profiles")}
    if "branding_style" in existing:
        op.drop_column("channel_profiles", "branding_style")
    if "branding_opacity" in existing:
        op.drop_column("channel_profiles", "branding_opacity")
