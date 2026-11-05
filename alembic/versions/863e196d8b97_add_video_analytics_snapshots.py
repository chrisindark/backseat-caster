"""add_video_analytics_snapshots

Revision ID: 863e196d8b97
Revises: e6f7a8b9c0d1
Create Date: 2026-11-04 19:13:37.424619

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '863e196d8b97'
down_revision: str | Sequence[str] | None = 'e6f7a8b9c0d1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if 'video_analytics_snapshots' not in tables:
        op.create_table(
            'video_analytics_snapshots',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('job_id', sa.String(length=64), nullable=False),
            sa.Column('clip_id', sa.String(length=128), nullable=False),
            sa.Column('youtube_video_id', sa.String(length=64), nullable=False),
            sa.Column('recorded_at', sa.DateTime(), nullable=False),
            sa.Column('published_at', sa.DateTime(), nullable=True),
            sa.Column('hours_since_publish', sa.Float(), nullable=False),
            sa.Column('view_count', sa.Integer(), nullable=False),
            sa.Column('like_count', sa.Integer(), nullable=False),
            sa.Column('comment_count', sa.Integer(), nullable=False),
            sa.Column('raw_payload', sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(['job_id'], ['render_jobs.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_video_analytics_snapshots_clip_id'), 'video_analytics_snapshots', ['clip_id'], unique=False)
        op.create_index(op.f('ix_video_analytics_snapshots_hours_since_publish'), 'video_analytics_snapshots', ['hours_since_publish'], unique=False)
        op.create_index(op.f('ix_video_analytics_snapshots_job_id'), 'video_analytics_snapshots', ['job_id'], unique=False)
        op.create_index(op.f('ix_video_analytics_snapshots_recorded_at'), 'video_analytics_snapshots', ['recorded_at'], unique=False)
        op.create_index(op.f('ix_video_analytics_snapshots_youtube_video_id'), 'video_analytics_snapshots', ['youtube_video_id'], unique=False)

    if 'render_jobs' in tables:
        existing_cols = {c['name'] for c in inspector.get_columns('render_jobs')}
        with op.batch_alter_table('render_jobs') as batch_op:
            if 'latest_view_count' not in existing_cols:
                batch_op.add_column(sa.Column('latest_view_count', sa.Integer(), nullable=True, server_default='0'))
            if 'latest_like_count' not in existing_cols:
                batch_op.add_column(sa.Column('latest_like_count', sa.Integer(), nullable=True, server_default='0'))
            if 'latest_comment_count' not in existing_cols:
                batch_op.add_column(sa.Column('latest_comment_count', sa.Integer(), nullable=True, server_default='0'))
            if 'velocity_3h' not in existing_cols:
                batch_op.add_column(sa.Column('velocity_3h', sa.Integer(), nullable=True, server_default='0'))
            if 'velocity_24h' not in existing_cols:
                batch_op.add_column(sa.Column('velocity_24h', sa.Integer(), nullable=True, server_default='0'))
            if 'metrics_last_polled_at' not in existing_cols:
                batch_op.add_column(sa.Column('metrics_last_polled_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if 'render_jobs' in tables:
        existing_cols = {c['name'] for c in inspector.get_columns('render_jobs')}
        with op.batch_alter_table('render_jobs') as batch_op:
            if 'metrics_last_polled_at' in existing_cols:
                batch_op.drop_column('metrics_last_polled_at')
            if 'velocity_24h' in existing_cols:
                batch_op.drop_column('velocity_24h')
            if 'velocity_3h' in existing_cols:
                batch_op.drop_column('velocity_3h')
            if 'latest_comment_count' in existing_cols:
                batch_op.drop_column('latest_comment_count')
            if 'latest_like_count' in existing_cols:
                batch_op.drop_column('latest_like_count')
            if 'latest_view_count' in existing_cols:
                batch_op.drop_column('latest_view_count')

    if 'video_analytics_snapshots' in tables:
        op.drop_index(op.f('ix_video_analytics_snapshots_youtube_video_id'), table_name='video_analytics_snapshots')
        op.drop_index(op.f('ix_video_analytics_snapshots_recorded_at'), table_name='video_analytics_snapshots')
        op.drop_index(op.f('ix_video_analytics_snapshots_job_id'), table_name='video_analytics_snapshots')
        op.drop_index(op.f('ix_video_analytics_snapshots_hours_since_publish'), table_name='video_analytics_snapshots')
        op.drop_index(op.f('ix_video_analytics_snapshots_clip_id'), table_name='video_analytics_snapshots')
        op.drop_table('video_analytics_snapshots')
