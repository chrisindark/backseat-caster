"""Add separate upload/analytics unit counters to youtube_quota_usage

Separate YouTube quota gates: upload_units_used (charged 1,600 per upload)
and analytics_units_used (charged 1 per 50-video statistics batch). Both
sum into units_used (the shared 10,000-unit daily pool); each has its own
budget so exhausting one does not block the other.

Revision ID: a1b2c3d4e5f6
Revises: f8b1c2d3e4a5
Create Date: 2026-11-05

"""
from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f6"
down_revision = "f8b1c2d3e4a5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("youtube_quota_usage") as batch_op:
        batch_op.add_column(
            sa.Column("upload_units_used", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column("analytics_units_used", sa.Integer(), nullable=False, server_default="0")
        )
    # Backfill: existing totals are all upload charges.
    op.execute(
        "UPDATE youtube_quota_usage SET upload_units_used = units_used WHERE units_used IS NOT NULL"
    )


def downgrade() -> None:
    with op.batch_alter_table("youtube_quota_usage") as batch_op:
        batch_op.drop_column("analytics_units_used")
        batch_op.drop_column("upload_units_used")
