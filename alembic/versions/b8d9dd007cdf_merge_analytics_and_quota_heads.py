"""merge_analytics_and_quota_heads

Revision ID: b8d9dd007cdf
Revises: a1b2c3d4e5f6, b2c3d4e5f6a7
Create Date: 2026-11-05 19:43:55.850039

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b8d9dd007cdf'
down_revision: Union[str, Sequence[str], None] = ('a1b2c3d4e5f6', 'b2c3d4e5f6a7')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
