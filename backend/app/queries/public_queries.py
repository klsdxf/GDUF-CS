"""Batch-load public tournament data from a single bounded read transaction."""
from collections import defaultdict
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, tuple_

from ..db import Competition, Match, Member, Registration, RosterSnapshot, Session, engine
from ..roster import serialize
from ..security import fail

SHANGHAI = ZoneInfo('Asia/Shanghai')
MATCH_FIELDS = ('id', 'competition_id', 'stage_id', 'code', 'round', 'group', 'bracket',
                'source_a', 'source_b', 'best_of', 'scheduled_at', 'status', 'confirmed', 'version')
TEAM_FIELDS = ('name', 'english_name', 'emblem_text', 'poster_title_lines', 'description', 'logo')
MAP_FIELDS = ('map_name', 'score_a', 'score_b', 'overtime')
RESULT_FIELDS = ('result_type', 'winner', 'reason', 'wins_a', 'wins_b', 'complete')


def snapshot_read(query):
    if engine.dialect.name == 'postgresql':
        connection_options = dict(isolation_level='REPEATABLE READ', postgresql_readonly=True)
        with engine.connect().execution_options(**connection_options) as connection:
            with Session(bind=connection) as db:
                return query(db)
    with Session() as db:
        return query(db)


def team_versions(db, by_id, pairs):
    if not pairs:
        return {}
    versions = tuple_(RosterSnapshot.registration_id, RosterSnapshot.version)
    snapshots = {(r.registration_id, r.version): r for r in db.scalars(
        select(RosterSnapshot).where(versions.in_(pairs)))}
    member_versions = tuple_(Member.registration_id, Member.version)
    members = defaultdict(list)
    for member in db.scalars(select(Member).where(member_versions.in_(pairs)).order_by(
            Member.registration_id, Member.version, Member.id)):
        members[(member.registration_id, member.version)].append({
            'nickname': member.nickname, 'role': member.role, 'captain': member.captain,
        })
    output = {}
    for team_id, version in pairs:
        team = by_id.get(team_id)
        snapshot = snapshots.get((team_id, version))
        if not team or not snapshot:
            fail('ROSTER_HISTORY_MISSING', '比赛名单资料暂不可用', 503)
        output[(team_id, version)] = {
            'id': team.id, 'competition_id': team.competition_id, 'code': team.code,
            **{field: getattr(snapshot, field) for field in TEAM_FIELDS},
            'members': members[(team_id, version)],
        }
    return output


def team_dto(db, team, version=None):
    version = team.version if version is None else version
    ref = team.id, version
    return team_versions(db, {team.id: team}, {ref})[ref]


def match_dtos(db, matches):
    ids = {team for match in matches for team in (match.a, match.b) if team}
    teams = {team.id: team for team in db.scalars(select(Registration).where(Registration.id.in_(ids)))} if ids else {}

    def pair(match, team):
        if not team:
            return None
        registration = teams.get(team)
        version = (match.rosters or {}).get(team)
        if not registration or registration.competition_id != match.competition_id or (match.published and not version):
            fail('ROSTER_HISTORY_MISSING', '比赛名单资料暂不可用', 503)
        return team, version if version is not None else registration.version

    references = [[pair(match, match.a), pair(match, match.b)] for match in matches]
    roster = team_versions(db, teams, {ref for row in references for ref in row if ref})
    output = []
    for match, refs in zip(matches, references, strict=True):
        result = {}
        if match.confirmed:
            result = {field: match.result[field] for field in RESULT_FIELDS if field in match.result}
            if 'maps' in match.result:
                result['maps'] = [{field: item[field] for field in MAP_FIELDS if field in item}
                                  for item in match.result['maps']]
        values = serialize(match)
        data = {field: values[field] for field in MATCH_FIELDS}
        if match.bracket == 'third':
            data['label'] = '季军赛'
        output.append({**data, 'result': result, 'teams': [roster[ref] if ref else None for ref in refs]})
    return output


def match_dto(db, match):
    return match_dtos(db, [match])[0]


def ordered_matches(query):
    return query.order_by(Match.scheduled_at.asc().nulls_last(), Match.round, Match.code, Match.id)


def published_matches(competition_id, *, date=None, stage=None, status=None):
    query = select(Match).where(Match.competition_id == competition_id, Match.published.is_(True))
    if date:
        start = datetime.combine(date, time.min, SHANGHAI).astimezone(timezone.utc)
        end = datetime.combine(date + timedelta(days=1), time.min, SHANGHAI).astimezone(timezone.utc)
        query = query.where(Match.scheduled_at >= start, Match.scheduled_at < end)
    if stage:
        query = query.where(Match.stage_id == stage)
    if status:
        query = query.where(Match.status == status)
    return ordered_matches(query)


def competitions_with_counts(db, *, offset=0, limit=None):
    counts = (select(Registration.competition_id, func.count().label('team_count'))
              .where(Registration.active.is_(True)).group_by(Registration.competition_id).subquery())
    query = (select(Competition, func.coalesce(counts.c.team_count, 0))
             .outerjoin(counts, counts.c.competition_id == Competition.id)
             .where(Competition.published.is_(True))
             .order_by(Competition.is_default.desc(), Competition.season.desc(), Competition.id))
    return db.execute(query.offset(offset).limit(limit))
