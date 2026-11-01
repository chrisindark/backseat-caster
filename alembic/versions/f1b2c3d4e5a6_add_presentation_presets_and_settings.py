"""add presentation presets and settings to channel profiles

Revision ID: f1b2c3d4e5a6
Revises: d8a2c4e6f1b3
Create Date: 2026-10-31 23:40:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f1b2c3d4e5a6"
down_revision: str | None = "d8a2c4e6f1b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = (
    ("presentation_preset", sa.String(length=32)),
    ("watermark_start_seconds", sa.Float()),
    ("watermark_end_seconds", sa.Float()),
    ("hook_enabled", sa.Boolean()),
    ("hook_text", sa.String(length=255)),
    ("hook_start_seconds", sa.Float()),
    ("hook_duration_seconds", sa.Float()),
    ("hook_position", sa.String(length=32)),
    ("kill_effects_enabled", sa.Boolean()),
    ("bg_music_path", sa.String(length=1024)),
    ("bg_music_volume", sa.Float()),
    ("loop_optimization", sa.Boolean()),
    ("target_fps", sa.Integer()),
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "channel_profiles" not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns("channel_profiles")}
    for name, coltype in _COLUMNS:
        if name in existing:
            continue
        op.add_column("channel_profiles", sa.Column(name, coltype, nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "channel_profiles" not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns("channel_profiles")}
    for name, _coltype in _COLUMNS:
        if name in existing:
            op.drop_column("channel_profiles", name)
