"""Add operation receipts, cache outbox, and optimistic versions."""
from alembic import op
import sqlalchemy as sa

revision = '007'
down_revision = '006'
VERSIONED = ('competitions', 'stages', 'announcements', 'live_streams')


def upgrade():
    op.create_table(
        'operation_receipts',
        sa.Column('actor_id', sa.Integer(), primary_key=True),
        sa.Column('action', sa.String(40), primary_key=True),
        sa.Column('resource_id', sa.String(100), primary_key=True),
        sa.Column('key_hash', sa.String(64), primary_key=True),
        sa.Column('request_hash', sa.String(64), nullable=False),
        sa.Column('response_status', sa.Integer(), nullable=False),
        sa.Column('response_body', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True)),
    )
    op.create_table(
        'cache_invalidation_events',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('retry_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('last_error', sa.String(64)),
    )
    op.create_index('ix_cache_outbox_pending', 'cache_invalidation_events', ['retry_at', 'id'],
                    postgresql_where=sa.text('completed_at IS NULL'),
                    sqlite_where=sa.text('completed_at IS NULL'))
    op.create_table(
        'redis_runtime_state',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('run_id', sa.String(64)),
        sa.Column('epoch', sa.String(64)),
        sa.Column('login_blocked_until', sa.DateTime(timezone=True)),
    )
    for table in VERSIONED:
        op.add_column(table, sa.Column('version', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('audit_logs', sa.Column('actor_id', sa.Integer()))
    op.add_column('audit_logs', sa.Column('request_id', sa.String(24)))


def downgrade():
    op.drop_column('audit_logs', 'request_id')
    op.drop_column('audit_logs', 'actor_id')
    for table in VERSIONED:
        op.drop_column(table, 'version')
    for table in ('redis_runtime_state', 'cache_invalidation_events', 'operation_receipts'):
        op.drop_table(table)
