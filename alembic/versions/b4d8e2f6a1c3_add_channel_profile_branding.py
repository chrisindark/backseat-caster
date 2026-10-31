"""add branded intro/outro card columns to channel profiles

Revision ID: b4d8e2f6a1c3
Revises: f8b1c2d3e4a5
Create Date: 2026-10-31 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b4d8e2f6a1c3"
down_revision: str | None = "f8b1c2d3e4a5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Branded intro/outro cards moved from ``BRANDING_*`` settings into the
#: channel profile. Columns stay nullable: a row created before this revision
#: falls back to the env defaults instead of rendering unbranded.
_COLUMNS: tuple[tuple[str, sa.types.TypeEngine], ...] = (
    ("branding_enabled", sa.Boolean()),
    ("branding_intro", sa.Boolean()),
    ("branding_outro", sa.Boolean()),
    ("branding_intro_seconds", sa.Float()),
    ("branding_outro_seconds", sa.Float()),
    ("branding_intro_title", sa.String(length=255)),
    ("branding_intro_subtitle", sa.String(length=255)),
    ("branding_outro_title", sa.String(length=255)),
    ("branding_outro_subtitle", sa.String(length=255)),
    ("branding_background_color", sa.String(length=16)),
    ("branding_accent_color", sa.String(length=16)),
    ("branding_text_color", sa.String(length=16)),
    ("branding_font_path", sa.String(length=1024)),
)


def upgrade() -> None:
    # The table only exists from revision e1a2b3c4d5e6 onwards; guard so this
    # revision also applies to databases built before the channel profile.
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "channel_profiles" not in inspector.get_table_names():
        return

    existing = {column["name"] for column in inspector.get_columns("channel_profiles")}
    for name, column_type in _COLUMNS:
        if name in existing:
            continue
        op.add_column("channel_profiles", sa.Column(name, column_type, nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "channel_profiles" not in inspector.get_table_names():
        return

    existing = {column["name"] for column in inspector.get_columns("channel_profiles")}
    for name, _column_type in _COLUMNS:
        if name in existing:
            op.drop_column("channel_profiles", name)
