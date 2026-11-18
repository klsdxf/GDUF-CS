import re
from datetime import datetime, timezone

from sqlalchemy import delete, func, select

from ..db import Audit, Claim, Competition, ImportBatch, Match, Member, Registration, RosterSnapshot, Stage, now
from ..infrastructure.request_context import request_id
from ..schemas import CompetitionPresentation
from ..security import fail
from .locking import lock_owner
from .operations import receipt, record


def serialize(obj):
    return {col.name: (value.replace(tzinfo=timezone.utc) if isinstance(value,datetime) and value.tzinfo is None else value) for col in obj.__table__.columns for value in [getattr(obj,col.name)]}


def presentation_config(config):
    if 'presentation' in config:
        config={**config,'presentation':CompetitionPresentation.model_validate(config['presentation']).model_dump()}
    return config


def competition(db, key, lock=False):
    q = select(Competition).where((Competition.id == key) | (Competition.slug == key))
    if lock:
        q = q.with_for_update().execution_options(populate_existing=True)
    value = db.scalar(q)
    if not value:
        fail('NOT_FOUND', '赛事不存在', 404)
    return value


def audit(db, action, entity, payload):
    db.add(Audit(action=action, entity_id=entity, payload=payload, request_id=request_id.get() or None))


def private_team(db, team):
    return {**serialize(team), 'members': [serialize(x) for x in db.scalars(select(Member).where(Member.registration_id == team.id, Member.version == team.version))]}


def validate_roster(db, c, teams, mode, revision=False):
    errors, seen_ids, seen_names, seen_codes = [], set(), set(), set()
    existing = {x.code: x for x in db.scalars(select(Registration).where(Registration.competition_id == c.id, Registration.active == True))}
    updating = {x['code'] for x in teams}
    for claim in db.scalars(select(Claim).where(Claim.competition_id == c.id)):
        if not any(t.id == claim.registration_id and code in updating and mode == 'update' for code, t in existing.items()):
            seen_ids.add(claim.steam_id)
    for i, t in enumerate(teams):
        def err(message, column='队伍编号', sheet='队伍', row=None, code='INVALID_ROSTER'):
            errors.append({'sheet': sheet, 'row': row or t.get('_row', i + 2), 'column': column, 'team_code': t.get('code'), 'code': code, 'message': message})
        if not t.get('code') or len(t['code']) > 32 or t['code'] in seen_codes:
            err('队伍编号必填、最多32字且不能重复')
        seen_codes.add(t.get('code'))
        if t.get('code') in existing and mode == 'create':
            err('编号已存在，请选择更新模式', code='TEAM_EXISTS')
        if not t.get('name') or len(t['name']) > 100 or t['name'] in seen_names or any(v.name == t['name'] and k not in updating for k,v in existing.items()):
            err('队伍名称必填、最多100字且同届不能重名', '队伍名称')
        seen_names.add(t.get('name'))
        if not t.get('contact') or len(t['contact']) > 200:
            err('联系方式必填且最多200字', '队长联系方式')
        if len(t.get('english_name','')) > 120 or len(t.get('emblem_text','')) > 12 or len(t.get('poster_title_lines',[])) > 2 or any(not isinstance(x,str) or len(x)>120 for x in t.get('poster_title_lines',[])):
            err('英文队名最多120字，徽章缩写最多12字，海报标题最多两行')
        members = t.get('members', [])
        regular = [m for m in members if m.get('role') == '正式']
        captains = [m for m in members if m.get('captain')]
        if len(regular) != 5 or len(members) > 7 or len(captains) != 1 or captains[0].get('role') != '正式':
            err('每队必须五名正式、最多两名替补，且有一名正式队长')
        for m in members:
            if not isinstance(m.get('steam_id'), str) or not re.fullmatch(r'7656119\d{10}', m.get('steam_id', '')):
                err('SteamID64 必须为17位原始文本；数值单元格请重新填写', 'Steam ID', '成员', m.get('_row'))
            if m.get('steam_id') in seen_ids:
                err('该 Steam ID 在本赛事重复占用', 'Steam ID', '成员', m.get('_row'), 'MEMBER_CONFLICT')
            seen_ids.add(m.get('steam_id'))
            if not m.get('nickname') or len(m['nickname']) > 100 or m.get('role') not in ('正式', '替补'):
                err('昵称必填且最多100字，成员类型必须为正式或替补', '游戏昵称', '成员', m.get('_row'))
    if len(set(existing) | seen_codes) > c.team_limit:
        errors.append({'code': 'TEAM_LIMIT', 'message': '超过赛事参赛队伍上限'})
    if not revision and db.scalar(select(Stage.id).where(Stage.competition_id == c.id, Stage.status != 'draft')):
        errors.append({'code': 'ROSTER_LOCKED', 'message': '已生成赛程，普通名单操作已锁定'})
    return errors


def save_roster(db, c, teams, mode, revision=False):
    errors = validate_roster(db, c, teams, mode, revision)
    if errors:
        fail('INVALID_ROSTER', '名单校验未通过', details=errors)
    targets = []
    for t in teams:
        team = db.scalar(select(Registration).where(Registration.competition_id == c.id, Registration.code == t['code']))
        if not team:
            team = Registration(competition_id=c.id, code=t['code'], name=t['name'], contact=t['contact'])
            db.add(team)
            db.flush()
        else:
            db.execute(delete(Claim).where(Claim.registration_id == team.id))
            team.version += 1
        targets.append((team, t))
    db.flush()
    for team, t in targets:
        for field in ('name', 'contact', 'description', 'logo', 'english_name', 'emblem_text', 'poster_title_lines'):
            if field in t:
                setattr(team, field, t[field])
        team.active = True
        db.add(RosterSnapshot(registration_id=team.id,version=team.version,name=team.name,description=team.description,logo=team.logo,english_name=team.english_name,emblem_text=team.emblem_text,poster_title_lines=team.poster_title_lines))
        for m in t['members']:
            db.add(Member(registration_id=team.id, version=team.version, **{k:m[k] for k in ('nickname','steam_id','role','captain')}))
            db.add(Claim(competition_id=c.id, steam_id=m['steam_id'], registration_id=team.id))
    c.revision += 1
    audit(db, 'roster.save', c.id, {'codes': [t['code'] for t in teams], 'revision': c.revision})
    return [team.id for team, t in targets]


def apply_roster_revision(key, payload, db):
    t,c=lock_owner(db, Registration, key, '队伍不存在')
    if not payload.get('reason'):fail('REASON','名单变更须填写原因')
    if payload.get('expected_version')!=t.version:fail('VERSION','名单版本已变更',409)
    payload['code']=t.code
    before={'version': t.version, 'name': t.name}
    ids=save_roster(db,c,[payload],'update',True)
    audit(db,'roster.revise',t.id,{'before':before,'after':{'version': t.version, 'name': t.name},
                                  'reason':payload['reason']})
    return {'data':{'ids':ids,'message':'既有比赛仍引用发布时的名单版本；变更仅影响后续新增比赛'}}


def update_competition(key, payload, db):
    if payload.get('is_default'):
        competitions = list(db.scalars(select(Competition).order_by(Competition.id).with_for_update()
                                       .execution_options(populate_existing=True)))
        c = next((item for item in competitions if key in (item.id, item.slug)), None)
        if not c:
            fail('NOT_FOUND', '赛事不存在', 404)
    else:
        c = competition(db, key, True)
    if payload.get('expected_version', c.version) != c.version:
        fail('VERSION', '赛事资料已变更，请刷新后重试', 409)
    if 'config' in payload:payload['config']=presentation_config({**c.config,**payload['config']})
    if payload.get('status',c.status) not in ('draft','roster_preparation','scheduling','ongoing','completed','archived'):fail('STATUS','无效赛事状态')
    if c.published and payload.get('status')=='draft':fail('STATUS','已发布赛事不能退回草稿；结束后可归档',409)
    if payload.get('team_limit',c.team_limit) not in range(2,33):fail('TEAM_LIMIT','队伍上限须在2至32之间')
    if 'team_limit' in payload:
        active = db.scalar(select(func.count()).select_from(Registration).where(
            Registration.competition_id == c.id, Registration.active.is_(True)))
        if payload['team_limit'] < active:
            fail('TEAM_LIMIT', '参赛上限不能小于现有队伍数', 409)
    if payload.get('focus_match_id'):
        match = db.get(Match, payload['focus_match_id'])
        if not match or match.competition_id != c.id:
            fail('CROSS_COMPETITION', '焦点比赛必须属于本届赛事')
    for k in ('name','season','organizer','description','rules','map_pool','team_limit','config','focus_match_id','status'):
        if k in payload:
            setattr(c,k,payload[k])
    if payload.get('is_default'):
        for other in competitions:
            if other.id != c.id and other.is_default:
                other.version += 1
            other.is_default = other.id == c.id
    elif 'is_default' in payload:c.is_default=False
    c.version += 1
    audit(db, 'competition.edit', c.id, {'fields': sorted(payload), 'version': c.version})
    return {'data': serialize(c)}


def apply_competition_publication(key, db):
    c = competition(db, key, True)
    if c.published:
        return {'data': serialize(c)}
    if not c.rules or not c.map_pool:
        fail('CONFIG', '发布前请填写规则和地图池')
    c.published = True
    c.version += 1
    if c.status == 'draft': c.status = 'roster_preparation'
    audit(db, 'competition.publish', c.id, {})
    return {'data': serialize(c)}


def withdraw_registration(key, db):
    t,c = lock_owner(db, Registration, key, '队伍不存在')
    if db.scalar(select(Match.id).where((Match.a == key)|(Match.b == key))): fail('REFERENCED','队伍已关联赛程，不能撤销',409)
    t.active = False; c.revision += 1
    db.execute(delete(Claim).where(Claim.registration_id == key))
    audit(db,'roster.withdraw',key,{})
    return {'data':True}


def commit_roster_import(key, payload, db):
    b,c=lock_owner(db, ImportBatch, key, '批次不存在')
    identity, fingerprint, previous = receipt(db, 'roster.import', key, payload.get('idempotency_key'),
                                             {'file_hash': b.file_hash, 'mode': b.mode, 'revision': b.revision})
    if previous:
        return previous.response_body
    if b.status == 'committed':
        fail('IMPORT_COMMITTED', '该预览已提交，请查看导入记录', 409)
    if b.revision!=c.revision or b.expires_at.replace(tzinfo=timezone.utc)<now(): fail('ROSTER_VERSION_CONFLICT','名单已变化或预览已过期，请重新预览',409)
    if b.payload['errors']: fail('IMPORT_ERRORS','预览有错误，不能提交')
    save_roster(db,c,b.payload['teams'],b.mode)
    b.status='committed'
    summary = {k: b.payload[k] for k in ('summary','team_count','member_count')}
    b.payload = {**summary, 'errors': [], 'differences': []}
    audit(db,'import.commit',b.id,{'hash':b.file_hash})
    return record(db, identity, fingerprint, {'data':serialize(b)})
