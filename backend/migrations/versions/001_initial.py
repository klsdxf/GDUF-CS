"""Initial relational schema."""
from alembic import op
from app.db import Base
revision = '001'
down_revision = None


def _initial_tables():
    # Later visit tables have their own migration and must not be created at 001.
    return [table for table in Base.metadata.sorted_tables
            if table.name not in ('visit_visitor_days', 'visit_daily_totals')]

def upgrade():
    Base.metadata.create_all(op.get_bind(), tables=_initial_tables())

def downgrade():
    Base.metadata.drop_all(op.get_bind(), tables=_initial_tables())
