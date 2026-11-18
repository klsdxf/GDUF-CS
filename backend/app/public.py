from datetime import date as CalendarDate, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from .db import Advancement, Announcement, LiveStream, Match, Registration, Stage, now
from .infrastructure.cache import cached
from .queries.public_queries import (
    competitions_with_counts, match_dto, match_dtos, published_matches, snapshot_read,
    team_dto, team_versions,
)
from .roster import competition, serialize
from .results import standings
from .schemas_public import (
    Data, PublicAnnouncement, PublicBracket, PublicCompetitionCount, PublicHome, PublicMatch,
    PublicStage, PublicStream, PublicTeam, PublicTeamDetail, Standing,
)
from .security import fail

router = APIRouter(prefix='/api/v1')
api = router.get
Status = Literal['unscheduled', 'scheduled', 'ongoing', 'postponed', 'cancelled', 'completed']


def read(schema, route, parameters, query):
    def load():
        return schema.model_validate({'data': snapshot_read(query)}).model_dump(mode='json', exclude_unset=True)
    return cached(route, parameters, load)


def public_c(db, key):
    c = competition(db, key)
    if not c.published:
        fail('NOT_FOUND', '赛事尚未公布', 404)
    return c


def c_dto(c):
    data = {**{field: getattr(c, field) for field in
               ('id', 'slug', 'name', 'season', 'organizer', 'description', 'rules',
                'map_pool', 'status', 'team_limit', 'is_default')},
            'presentation': c.config.get('presentation', {})}
    if c.config.get('competition_format') == 'single':
        data['competition_format'] = 'single'
    return data


def announcement_dto(a):
    fields = serialize(a)
    return {field: fields[field] for field in
            ('id', 'competition_id', 'title', 'body', 'published', 'pinned', 'publish_at',
             'category_label', 'display_order')}


def team_count(db, competition_id):
    return db.scalar(select(func.count()).select_from(Registration).where(
        Registration.competition_id == competition_id, Registration.active.is_(True)))


def require_team(db, competition_id, team_id):
    team = db.get(Registration, team_id)
    if not team or team.competition_id != competition_id or not team.active:
        fail('NOT_FOUND', '战队不存在', 404)
    return team


def require_match(db, key):
    m = db.get(Match, key)
    if not m or not m.published:
        fail('NOT_FOUND', '比赛尚未公布', 404)
    public_c(db, m.competition_id)
    return m


def require_announcement(db, key):
    a = db.get(Announcement, key)
    if not a or not a.published or (a.publish_at.replace(tzinfo=timezone.utc) if a.publish_at.tzinfo is None
                                    else a.publish_at) > now():
        fail('NOT_FOUND', '公告尚未公布', 404)
    public_c(db, a.competition_id)
    return a


def require_stage(db, key):
    stage = db.get(Stage, key)
    if not stage or stage.status != 'published':
        fail('NOT_FOUND', '阶段尚未公布', 404)
    public_c(db, stage.competition_id)
    return stage


@api('/competitions', response_model=Data[list[PublicCompetitionCount]], response_model_exclude_unset=True)
def competitions():
    return read(Data[list[PublicCompetitionCount]], 'competitions', [],
                lambda db: [{**c_dto(c), 'team_count': count} for c, count in competitions_with_counts(db)])


def paged(rows, offset, limit):
    return {'data': rows[:limit], 'meta': {'next_offset': offset + limit if len(rows) > limit else None}}


@api('/pages/competitions')
def competition_page(offset: int = Query(0, ge=0, le=10000), limit: int = Query(25, ge=1, le=100)):
    def query(db):
        return [PublicCompetitionCount.model_validate({**c_dto(c), 'team_count': count})
                for c, count in competitions_with_counts(db, offset=offset, limit=limit + 1)]
    return paged(snapshot_read(query), offset, limit)


@api('/competitions/{key}', response_model=Data[PublicCompetitionCount], response_model_exclude_unset=True)
def get_competition(key: str):
    def query(db):
        c = public_c(db, key)
        return {**c_dto(c), 'team_count': team_count(db, c.id)}
    return read(Data[PublicCompetitionCount], 'competition', [key], query)


@api('/competitions/{key}/teams', response_model=Data[list[PublicTeam]])
def teams(key: str):
    def query(db):
        c = public_c(db, key)
        by_id = {t.id: t for t in db.scalars(select(Registration).where(
            Registration.competition_id == c.id, Registration.active.is_(True)).order_by(Registration.code, Registration.id))}
        pairs = [(t.id, t.version) for t in by_id.values()]
        items = team_versions(db, by_id, pairs)
        return [items[pair] for pair in pairs]
    return read(Data[list[PublicTeam]], 'teams', [key], query)


@api('/competitions/{key}/teams/{team_id}', response_model=Data[PublicTeamDetail], response_model_exclude_unset=True)
def team(key: str, team_id: str):
    def query(db):
        c = public_c(db, key)
        t = require_team(db, c.id, team_id)
        rows = list(db.scalars(published_matches(c.id).where((Match.a == t.id) | (Match.b == t.id))))
        return {**team_dto(db, t), 'matches': match_dtos(db, rows)}
    return read(Data[PublicTeamDetail], 'team', [key, team_id], query)


@api('/competitions/{key}/matches', response_model=Data[list[PublicMatch]], response_model_exclude_unset=True)
def matches(key: str, date: CalendarDate | None = None,
            stage: Annotated[str | None, Query(max_length=100)] = None, status: Status | None = None):
    if date and not 1900 <= date.year <= 9998:
        fail('DATE', '比赛日期超出查询范围')
    def query(db):
        c = public_c(db, key)
        rows = list(db.scalars(published_matches(c.id, date=date, stage=stage, status=status)))
        return match_dtos(db, rows)
    return read(Data[list[PublicMatch]], 'matches', [key, date.isoformat() if date else None, stage, status], query)


@api('/matches/{key}', response_model=Data[PublicMatch], response_model_exclude_unset=True)
def match(key: str):
    return read(Data[PublicMatch], 'match', [key], lambda db: match_dto(db, require_match(db, key)))


def published_stages(db, competition_id):
    return db.scalars(select(Stage).where(Stage.competition_id == competition_id, Stage.status == 'published')
                      .order_by(Stage.id))


@api('/competitions/{key}/stages', response_model=Data[list[PublicStage]])
def stages(key: str):
    fields = ('best_of', 'qualify', 'groups', 'grand_final_reset')
    return read(Data[list[PublicStage]], 'stages', [key],
                lambda db: [{'id': s.id, 'name': s.name, 'type': s.type,
                             'config': {k: v for k, v in s.config.items() if k in fields}}
                            for s in published_stages(db, public_c(db, key).id)])


@api('/stages/{key}/standings', response_model=Data[list[Standing]])
def stage_standings(key: str):
    return read(Data[list[Standing]], 'standings', [key], lambda db: standings(db, require_stage(db, key)))


@api('/stages/{key}/bracket', response_model=Data[PublicBracket], response_model_exclude_unset=True)
def bracket(key: str):
    def query(db):
        stage = require_stage(db, key)
        rows = list(db.scalars(select(Match).where(Match.stage_id == stage.id, Match.published.is_(True))
                               .order_by(Match.round, Match.code, Match.id)))
        dtos = match_dtos(db, rows)
        byes = []
        for m, dto in zip(rows, dtos, strict=True):
            if m.round > 1 and not m.group:
                for team, source in zip(dto['teams'], (m.source_a, m.source_b), strict=True):
                    if (team and not source) or source.startswith('group:'):
                        byes.append({'name': team['name'] if team else None, 'source': source})
        edges = db.scalars(select(Advancement).where(Advancement.source.in_([m.id for m in rows]),
                                                   Advancement.target.in_([m.id for m in rows]))
                           .order_by(Advancement.target, Advancement.slot))
        return {'matches': dtos, 'edges': [serialize(e) for e in edges], 'bye_sources': byes}
    return read(Data[PublicBracket], 'bracket', [key], query)


def announcement_query(competition_id):
    return (select(Announcement).where(Announcement.competition_id == competition_id,
                                       Announcement.published.is_(True), Announcement.publish_at <= now())
            .order_by(Announcement.pinned.desc(), Announcement.display_order,
                      Announcement.publish_at.desc(), Announcement.id))


@api('/competitions/{key}/announcements', response_model=Data[list[PublicAnnouncement]])
def announcements(key: str):
    return read(Data[list[PublicAnnouncement]], 'announcements', [key], lambda db: [
        announcement_dto(a) for a in db.scalars(announcement_query(public_c(db, key).id))])


@api('/pages/competitions/{key}/announcements')
def announcement_page(key: str, offset: int = Query(0, ge=0, le=10000),
                      limit: int = Query(25, ge=1, le=100)):
    def query(db):
        rows = db.scalars(announcement_query(public_c(db, key).id).offset(offset).limit(limit + 1))
        return [PublicAnnouncement.model_validate(announcement_dto(a)) for a in rows]
    return paged(snapshot_read(query), offset, limit)


@api('/announcements/{key}', response_model=Data[PublicAnnouncement])
def announcement(key: str):
    return read(Data[PublicAnnouncement], 'announcement', [key],
                lambda db: announcement_dto(require_announcement(db, key)))


@api('/competitions/{key}/live', response_model=Data[list[PublicStream]])
def live(key: str):
    return read(Data[list[PublicStream]], 'live', [key], lambda db: [
        serialize(s) for s in db.scalars(select(LiveStream).where(
            LiveStream.competition_id == public_c(db, key).id).order_by(LiveStream.id))])


@api('/competitions/{key}/home', response_model=Data[PublicHome], response_model_exclude_unset=True)
def home(key: str):
    def query(db):
        c = public_c(db, key)
        rows = list(db.scalars(published_matches(c.id)))
        focus = (next((m for m in rows if m.id == c.focus_match_id), None)
                 or next((m for m in rows if m.status == 'ongoing'), None)
                 or next((m for m in rows if not m.confirmed and m.status != 'cancelled'), None))
        stages = list(published_stages(db, c.id))
        dtos = match_dtos(db, rows)
        return {'competition': c_dto(c), 'team_count': team_count(db, c.id),
                'focus': dtos[rows.index(focus)] if focus else None, 'matches': dtos,
                'standings': standings(db, stages[0]) if stages else [],
                'stages': [{'id': s.id, 'name': s.name} for s in stages]}
    return read(Data[PublicHome], 'home', [key], query)
