"""add cta voiceover columns to channel profiles

Revision ID: d8a2c4e6f1b3
Revises: c7f1a9d3e5b2
Create Date: 2026-10-31 00:20:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d8a2c4e6f1b3"
down_revision: str | None = "c7f1a9d3e5b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = (
    ("cta_enabled", sa.Boolean()),
    ("cta_style", sa.String(length=16)),
    ("cta_seconds", sa.Float()),
    ("cta_headline", sa.String(length=255)),
    ("cta_subtitle", sa.String(length=255)),
    ("cta_speech_text", sa.Text()),
    ("cta_voice", sa.String(length=64)),
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
