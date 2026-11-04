"""add is_ignored and ignore_reason to videos

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-11-03 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e6f7a8b9c0d1"
down_revision: str | None = "d5e6f7a8b9c0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "videos" not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns("videos")}
    with op.batch_alter_table("videos") as batch_op:
        if "is_ignored" not in existing:
            batch_op.add_column(
                sa.Column("is_ignored", sa.Boolean(), nullable=False, server_default="0")
            )
            batch_op.create_index("ix_videos_is_ignored", ["is_ignored"], unique=False)
        if "ignore_reason" not in existing:
            batch_op.add_column(
                sa.Column("ignore_reason", sa.String(length=256), nullable=True)
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "videos" not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns("videos")}
    with op.batch_alter_table("videos") as batch_op:
        if "is_ignored" in existing:
            try:
                batch_op.drop_index("ix_videos_is_ignored")
            except Exception:
                pass
            batch_op.drop_column("is_ignored")
        if "ignore_reason" in existing:
            batch_op.drop_column("ignore_reason")
