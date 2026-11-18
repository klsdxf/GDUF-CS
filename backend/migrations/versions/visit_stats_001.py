"""Add short-lived visitor activity and daily access totals."""
from alembic import op
import sqlalchemy as sa

revision = 'visit_stats_001'
down_revision = '006'


def upgrade():
    op.create_table(
        'visit_visitor_days',
        sa.Column('stat_date', sa.Date(), primary_key=True),
        sa.Column('visitor_digest', sa.String(64), primary_key=True),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_visit_visitor_days_last_seen_at', 'visit_visitor_days', ['last_seen_at'])
    op.create_table(
        'visit_daily_totals',
        sa.Column('stat_date', sa.Date(), primary_key=True),
        sa.Column('uv', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('pv', sa.BigInteger(), nullable=False, server_default='0'),
        sa.CheckConstraint('uv >= 0 AND pv >= 0', name='ck_visit_daily_totals_nonnegative'),
    )


def downgrade():
    op.drop_table('visit_daily_totals')
    op.drop_index('ix_visit_visitor_days_last_seen_at', table_name='visit_visitor_days')
    op.drop_table('visit_visitor_days')
