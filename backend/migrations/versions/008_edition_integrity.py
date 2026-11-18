"""Reject cross-edition links and invalid confirmed winners."""
from alembic import op
import sqlalchemy as sa

revision = '008'
down_revision = '007'

LINKS = (
    ('matches', 'stage_id', 'stages'), ('matches', 'a', 'registrations'),
    ('matches', 'b', 'registrations'), ('matches', 'winner', 'registrations'),
    ('active_member_claims', 'registration_id', 'registrations'),
    ('live_streams', 'match_id', 'matches'), ('match_advancements', 'source', 'matches'),
    ('match_advancements', 'target', 'matches'),
)
CHECKS = {
    'matches': (
        ('ck_match_winner', 'winner IS NULL OR (a IS NOT NULL AND winner = a) OR (b IS NOT NULL AND winner = b)'),
        ('ck_match_confirmed_sides', 'NOT confirmed OR (a IS NOT NULL AND b IS NOT NULL AND winner IS NOT NULL)'),
    ),
    'match_advancements': (
        ('ck_advancement_outcome', "outcome IN ('winner','loser')"),
        ('ck_advancement_slot', "slot IN ('a','b')"),
    ),
}


def verify_data(connection):
    errors = []
    for table, column, target in LINKS:
        identity = 'l.registration_id' if table == 'active_member_claims' else 'l.id'
        source = ('JOIN matches s ON s.id = l.source ' if table == 'match_advancements' else '')
        edition = 's.competition_id' if source else 'l.competition_id'
        found = connection.execute(sa.text(
            f'SELECT {identity} FROM {table} l {source}LEFT JOIN {target} r ON r.id = l.{column} '
            f'WHERE l.{column} IS NOT NULL AND (r.id IS NULL OR r.competition_id <> {edition}) LIMIT 25'
        )).scalars().all()
        if found:
            errors.append(f'{table}.{column} ({len(found)} examples): {", ".join(found)}')
    for table, checks in CHECKS.items():
        for name, expression in checks:
            found = connection.execute(sa.text(
                f'SELECT id FROM {table} WHERE NOT ({expression}) LIMIT 25')).scalars().all()
            if found:
                errors.append(f'{name}: {", ".join(found)}')
    metadata = sa.MetaData()
    matches = sa.Table('matches', metadata, autoload_with=connection)
    roster = sa.Table('roster_snapshots', metadata, autoload_with=connection)
    versions = set(connection.execute(sa.select(roster.c.registration_id, roster.c.version)).tuples())
    missing = []
    for match in connection.execute(sa.select(matches.c.id, matches.c.a, matches.c.b, matches.c.rosters)
                                    .where(matches.c.published.is_(True))).mappings():
        for slot in ('a', 'b'):
            team = match[slot]
            if team and (team, (match['rosters'] or {}).get(team)) not in versions and len(missing) < 25:
                missing.append(f'{match["id"]}:{slot}')
    if missing:
        errors.append('missing historical roster pins: ' + ', '.join(missing))
    if errors:
        raise RuntimeError('Resolve historical inconsistencies before migration: ' + '; '.join(errors))


def add_constraints():
    op.add_column('match_advancements', sa.Column('competition_id', sa.String()))
    op.execute(sa.text(
        'UPDATE match_advancements SET competition_id = '
        '(SELECT competition_id FROM matches WHERE matches.id = match_advancements.source)'
    ))
    tables = dict.fromkeys(table for table, _, _ in LINKS)
    for table in tables:
        with op.batch_alter_table(table) as batch:
            if table == 'match_advancements':
                batch.alter_column('competition_id', existing_type=sa.String(), nullable=False)
                batch.create_foreign_key('fk_advancement_competition', 'competitions', ['competition_id'], ['id'])
            for source, column, target in LINKS:
                if source == table:
                    batch.create_foreign_key(f'fk_{source}_{column}_edition', target,
                                             [column, 'competition_id'], ['id', 'competition_id'])
            for name, expression in CHECKS.get(table, ()):
                batch.create_check_constraint(name, expression)
    op.create_index('ix_audit_created_id', 'audit_logs', [sa.text('created_at DESC'), sa.text('id DESC')])
    op.create_index('ix_advancement_source', 'match_advancements', ['source'])


def upgrade():
    connection = op.get_bind()
    verify_data(connection)
    if connection.dialect.name != 'sqlite':
        add_constraints()
        return
    # SQLite rebuilds the referenced matches table to add constraints.
    with op.get_context().autocommit_block():
        connection.exec_driver_sql('PRAGMA foreign_keys=OFF')
        try:
            connection.exec_driver_sql('BEGIN IMMEDIATE')
            try:
                add_constraints()
                if connection.exec_driver_sql('PRAGMA foreign_key_check').first():
                    raise RuntimeError('SQLite foreign key check failed')
                connection.exec_driver_sql('COMMIT')
            except BaseException:
                connection.exec_driver_sql('ROLLBACK')
                raise
        finally:
            connection.exec_driver_sql('PRAGMA foreign_keys=ON')


def downgrade():
    raise RuntimeError('Restore the pre-release backup for a schema rollback; do not drop integrity constraints in place.')
