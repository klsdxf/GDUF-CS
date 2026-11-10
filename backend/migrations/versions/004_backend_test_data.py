"""Backend test data, independent result scenarios and import provenance."""
from alembic import op
import sqlalchemy as sa
from app.db import Base

revision = '004'
down_revision = '003'


def upgrade():
    bind = op.get_bind()
    # Older migrations create from current metadata on a fresh installation.
    for name in ('seed_batches','seed_entities','seed_previews'):
        Base.metadata.tables[name].create(bind, checkfirst=True)
    fields = {
        'competitions': [('data_origin', "VARCHAR(16) NOT NULL DEFAULT 'regular'"), ('seed_batch_id', 'VARCHAR REFERENCES seed_batches(id)')],
        'sponsors': [('data_origin', "VARCHAR(16) NOT NULL DEFAULT 'regular'"), ('seed_batch_id', 'VARCHAR REFERENCES seed_batches(id)')],
        'announcements': [('category_label', "VARCHAR(100) NOT NULL DEFAULT ''"), ('display_order', 'INTEGER NOT NULL DEFAULT 0')],
        'competition_result_pages': [('result_kind', "VARCHAR(16) NOT NULL DEFAULT 'official'")],
        'result_releases': [('result_kind', "VARCHAR(16) NOT NULL DEFAULT 'official'"), ('data_origin', "VARCHAR(16) NOT NULL DEFAULT 'regular'")],
    }
    for table, columns in fields.items():
        existing = {c['name'] for c in sa.inspect(bind).get_columns(table)}
        for name, ddl in columns:
            if name not in existing:
                op.execute(sa.text(f'ALTER TABLE {table} ADD COLUMN {name} {ddl}'))
    Base.metadata.tables['result_test_matches'].create(bind, checkfirst=True)


def downgrade():
    # The release history and source data must first be backed up by the operator.
    op.drop_table('result_test_matches')
    for table, columns in (
        ('result_releases', ('result_kind','data_origin')),
        ('competition_result_pages', ('result_kind',)),
        ('announcements', ('category_label','display_order')),
        ('sponsors', ('seed_batch_id','data_origin')),
        ('competitions', ('seed_batch_id','data_origin')),
    ):
        with op.batch_alter_table(table) as batch:
            for column in columns:
                batch.drop_column(column)
    for table in ('seed_entities','seed_previews','seed_batches'):
        op.drop_table(table)
