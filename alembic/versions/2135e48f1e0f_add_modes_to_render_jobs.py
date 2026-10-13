"""add_modes_to_render_jobs

Revision ID: 2135e48f1e0f
Revises: 9a1b2c3d4e5f
Create Date: 2026-10-13 06:42:15.613454

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2135e48f1e0f"
down_revision: str | Sequence[str] | None = "9a1b2c3d4e5f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "render_jobs", sa.Column("modes", sa.String(length=256), nullable=True)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("render_jobs", "modes")
