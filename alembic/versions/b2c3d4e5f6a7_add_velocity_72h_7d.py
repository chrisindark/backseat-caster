"""Add velocity_72h and velocity_7d columns to render_jobs

Extends the view-velocity windows to 72h and 7 days so slots are ranked
on views accumulated over a full week, not just the first 24 hours.

Revision ID: b2c3d4e5f6a7
Revises: 863e196d8b97
Create Date: 2026-11-05

"""
from alembic import op
import sqlalchemy as sa

revision = "b2c3d4e5f6a7"
down_revision = "863e196d8b97"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("render_jobs") as batch_op:
        batch_op.add_column(sa.Column("velocity_72h", sa.Integer(), nullable=True, server_default="0"))
        batch_op.add_column(sa.Column("velocity_7d", sa.Integer(), nullable=True, server_default="0"))


def downgrade() -> None:
    with op.batch_alter_table("render_jobs") as batch_op:
        batch_op.drop_column("velocity_7d")
        batch_op.drop_column("velocity_72h")
