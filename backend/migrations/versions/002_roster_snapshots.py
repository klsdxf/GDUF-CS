"""Freeze public team identity per roster version."""
from alembic import op
import sqlalchemy as sa
revision='002'
down_revision='001'

def upgrade():
    bind=op.get_bind()
    if not sa.inspect(bind).has_table('roster_snapshots'):
        op.create_table('roster_snapshots',sa.Column('registration_id',sa.String(),sa.ForeignKey('registrations.id'),primary_key=True),sa.Column('version',sa.Integer(),primary_key=True),sa.Column('name',sa.String(),nullable=False),sa.Column('description',sa.String(),nullable=False),sa.Column('logo',sa.String(),nullable=False))
    bind.execute(sa.text('INSERT INTO roster_snapshots (registration_id, version, name, description, logo) SELECT r.id, r.version, r.name, r.description, r.logo FROM registrations r WHERE NOT EXISTS (SELECT 1 FROM roster_snapshots s WHERE s.registration_id=r.id AND s.version=r.version)'))

def downgrade():
    op.drop_table('roster_snapshots')
