"""Final rankings, sponsorship and immutable public releases."""
from alembic import op
import sqlalchemy as sa
from app.db import Base
revision = '003'
down_revision = '002'
TABLES = ['competition_result_pages','result_placements','result_path_matches','sponsors','competition_partners','prizes','prize_allocations','result_releases']
def upgrade():
    bind=op.get_bind()
    for table in ('registrations','roster_snapshots'):
        existing={c['name'] for c in sa.inspect(bind).get_columns(table)}
        for col in (sa.Column('english_name',sa.String(120),nullable=False,server_default=''),sa.Column('emblem_text',sa.String(12),nullable=False,server_default=''),sa.Column('poster_title_lines',sa.JSON(),nullable=False,server_default='[]')):
            if col.name not in existing:op.add_column(table,col)
    for table in ('registrations','stages','matches'):
        keys=sa.inspect(bind).get_unique_constraints(table)+sa.inspect(bind).get_indexes(table)
        if not any(k['column_names']==['id','competition_id'] for k in keys):
            op.create_index('uq_'+table+'_id_competition',table,['id','competition_id'],unique=True)
    Base.metadata.create_all(op.get_bind(),tables=[Base.metadata.tables[t] for t in TABLES])
    if 'uq_presenting_partner' not in {x['name'] for x in sa.inspect(bind).get_indexes('competition_partners')}:op.create_index('uq_presenting_partner','competition_partners',['competition_id'],unique=True,sqlite_where=sa.text("tier = 'presenting'"),postgresql_where=sa.text("tier = 'presenting'"))
def downgrade():
    op.drop_index('uq_presenting_partner',table_name='competition_partners')
    with op.batch_alter_table('competition_result_pages') as batch:
        batch.drop_column('current_release_id')
    for t in reversed(TABLES): op.drop_table(t)
    for t in ('registrations','roster_snapshots'):
        with op.batch_alter_table(t) as batch:
            for col in ('english_name','emblem_text','poster_title_lines'): batch.drop_column(col)
