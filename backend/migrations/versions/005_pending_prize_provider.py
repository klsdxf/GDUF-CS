"""Allow a prize to be allocated before a sponsor is assigned."""
from alembic import op
import sqlalchemy as sa

revision = '005'
down_revision = '004'


def alter_provider(nullable):
    bind = op.get_bind()
    if bind.dialect.name != 'sqlite':
        op.alter_column('prizes', 'provider_partner_id', existing_type=sa.String(), nullable=nullable)
        return

    with op.get_context().autocommit_block():
        bind.exec_driver_sql('PRAGMA foreign_keys=OFF')
        try:
            bind.exec_driver_sql('BEGIN IMMEDIATE')
            try:
                with op.batch_alter_table('prizes') as batch:
                    batch.alter_column('provider_partner_id', existing_type=sa.String(), nullable=nullable)
                if bind.exec_driver_sql('PRAGMA foreign_key_check').first():
                    raise RuntimeError('Prize migration violates SQLite foreign keys')
                bind.exec_driver_sql('COMMIT')
            except BaseException:
                bind.exec_driver_sql('ROLLBACK')
                raise
        finally:
            bind.exec_driver_sql('PRAGMA foreign_keys=ON')


def upgrade():
    provider = next(column for column in sa.inspect(op.get_bind()).get_columns('prizes')
                    if column['name'] == 'provider_partner_id')
    if not provider['nullable']:
        alter_provider(True)


def downgrade():
    if op.get_bind().execute(sa.text('SELECT 1 FROM prizes WHERE provider_partner_id IS NULL LIMIT 1')).first():
        raise RuntimeError('Assign providers to pending prizes before downgrading to revision 004')
    alter_provider(False)
