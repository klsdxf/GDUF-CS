"""Pin missing team versions on previously qualified playoff matches."""
from alembic import op
import sqlalchemy as sa

revision = '006'
down_revision = '005'


def upgrade():
    conn = op.get_bind()
    metadata = sa.MetaData()
    matches, teams, logs, snapshots = [
        sa.Table(name, metadata, autoload_with=conn)
        for name in ('matches', 'registrations', 'audit_logs', 'roster_snapshots')
    ]
    playoff = sa.select(matches).where(matches.c.bracket == 'playoff')
    for match in conn.execute(playoff).mappings():
        versions = dict(match['rosters'] or {})
        for slot in ('a', 'b'):
            team = match[slot]
            if not team or team in versions or not match['source_' + slot].startswith('group:'):
                continue
            qualified_at = conn.scalar(sa.select(sa.func.max(logs.c.created_at)).where(
                logs.c.entity_id == match['stage_id'], logs.c.action == 'qualification.confirm'))
            version = conn.scalar(sa.select(teams.c.version).where(teams.c.id == team))
            if qualified_at:
                change = conn.scalar(sa.select(logs.c.payload).where(
                    logs.c.entity_id == team, logs.c.action == 'roster.revise',
                    logs.c.created_at > qualified_at
                ).order_by(logs.c.created_at, logs.c.id).limit(1))
                if change:
                    version = change['before']['version']
            # Without a qualification log, preserve the last visible roster.
            if conn.scalar(sa.select(snapshots.c.version).where(
                snapshots.c.registration_id == team, snapshots.c.version == version
            )) is None:
                raise RuntimeError(f'Missing roster snapshot for match {match["id"]}, team {team}')
            versions[team] = version
        if versions != match['rosters']:
            conn.execute(matches.update().where(matches.c.id == match['id']).values(rosters=versions))


def downgrade():
    # The old schema can read these pins. Removing them would discard history.
    pass
