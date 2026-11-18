from sqlalchemy import select

from ..db import Competition, Registration, RosterSnapshot
from ..security import fail


def lock_competition(db, competition_id):
    competition = db.scalar(select(Competition).where(Competition.id == competition_id)
                            .with_for_update().execution_options(populate_existing=True))
    if not competition:
        fail('NOT_FOUND', '赛事不存在', 404)
    return competition


def lock_owner(db, model, key, missing):
    # The first query retrieves only the owner ID, never a stale entity.
    competition_id = db.scalar(select(model.competition_id).where(model.id == key))
    if not competition_id:
        fail('NOT_FOUND', missing, 404)
    competition = lock_competition(db, competition_id)
    entity = db.get(model, key, populate_existing=True)
    if entity is None or entity.competition_id != competition.id:
        fail('NOT_FOUND', missing, 404)
    return entity, competition


def expect_version(value, expected):
    if expected is not None and expected != value.version:
        fail('VERSION', '数据已更新，请刷新后重试', 409,
             {'expected_version': expected, 'current_version': value.version})


def bind_rosters(db, match, slots, *, freeze=True):
    previous = match.rosters or {}
    originally_present = {match.a, match.b}
    if slots['a'] is not None and slots['a'] == slots['b']:
        fail('SAME_TEAM', '比赛双方不能是同一队伍', 409)
    versions = {}
    for team_id in filter(None, slots.values()):
        team = db.get(Registration, team_id)
        if not team or team.competition_id != match.competition_id:
            fail('CROSS_COMPETITION', '参赛队伍必须属于本届赛事', 409)
        if not freeze:
            continue
        version = previous.get(team_id) if team_id in originally_present else None
        if version is None and match.published and team_id in originally_present:
            fail('ROSTER_HISTORY_MISSING', '请核对比赛的历史名单版本', 409)
        if version is None:
            version = team.version
        if not db.get(RosterSnapshot, (team_id, version)):
            fail('ROSTER_HISTORY_MISSING', '缺少参赛队伍的名单版本', 409)
        versions[team_id] = version
    changed = (match.a, match.b, previous) != (slots['a'], slots['b'], versions)
    if changed:
        match.a, match.b, match.rosters = slots['a'], slots['b'], versions
        match.version += 1
    return changed


def require_frozen_rosters(db, match):
    for team in (match.a, match.b):
        version = (match.rosters or {}).get(team)
        if not team or not version or not db.get(RosterSnapshot, (team, version)):
            fail('ROSTER_HISTORY_MISSING', '请核对比赛双方的历史名单版本', 409)
