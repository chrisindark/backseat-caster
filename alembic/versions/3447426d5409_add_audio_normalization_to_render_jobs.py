"""add_audio_normalization_to_render_jobs

Revision ID: 3447426d5409
Revises: 2135e48f1e0f
Create Date: 2026-10-13 12:14:44.838084

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3447426d5409"
down_revision: str | Sequence[str] | None = "2135e48f1e0f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "render_jobs",
        sa.Column(
            "normalize_audio", sa.Boolean(), nullable=True, server_default=sa.true()
        ),
    )
    op.add_column(
        "render_jobs",
        sa.Column(
            "target_lufs", sa.Float(), nullable=True, server_default=sa.text("-14.0")
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("render_jobs", "target_lufs")
    op.drop_column("render_jobs", "normalize_audio")
