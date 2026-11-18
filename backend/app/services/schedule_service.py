import random
from sqlalchemy import select, delete
from ..db import *
from .roster_service import competition, serialize, audit
from ..security import authenticated, fail
from ..services.locking import bind_rosters, expect_version, lock_owner
from ..services.operations import command
from ..infrastructure.outbox import mark_public_change

from ..domain.brackets import generate_graph


def stages(key, db):
    c=competition(db,key)
    return {'data':[serialize(s) for s in db.scalars(select(Stage).where(Stage.competition_id==c.id))]}


def create_stage(payload, db):
    c=competition(db,payload['competition_id'],True)
    if payload.get('type') not in ('single','group_single','double'): fail('TYPE','请选择三种赛制之一')
    s=Stage(competition_id=c.id,name=payload['name'],type=payload['type'],config=payload.get('config',{}))
    db.add(s);db.flush()
    audit(db,'stage.create',s.id,payload)
    return {'data':serialize(s)}


def edit_stage(key, payload, db):
    s,_=lock_owner(db, Stage, key, '阶段不存在')
    expect_version(s, payload.get('expected_version'))
    if s.status!='draft': fail('LOCKED','请先作废草稿再修改',409)
    for k in ('name','config'):
        if k in payload:setattr(s,k,payload[k])
    s.version += 1
    return {'data':serialize(s)}


def entries(key, payload, db):
    s,_=lock_owner(db, Stage, key, '阶段不存在')
    expect_version(s, payload.get('expected_version'))
    if s.status!='draft':fail('LOCKED','已生成赛程，不能更换种子',409)
    valid=set(db.scalars(select(Registration.id).where(Registration.competition_id==s.competition_id,Registration.active==True)))
    values=payload.get('entries',[])
    if len(set(values))!=len(values) or not set(values)<=valid or not 2<=len(values)<=32:fail('ENTRIES','请选择2至32支有效队伍，种子不得重复')
    s.entries=values
    s.version += 1
    return {'data':serialize(s)}


def generate_schedule(db, key, payload):
    s,_=lock_owner(db, Stage, key, '阶段不存在')
    token = payload.get('idempotency_key')
    data = {k: v for k, v in payload.items() if k != 'idempotency_key'}
    def apply():
        return create_schedule_preview(db, s, token, data)
    return command(db, 'schedule.generate', key, token, data, apply) if token is not None else apply()


def create_schedule_preview(db, s, token, payload):
    key = s.id
    if s.status!='draft':
        if token is not None and s.generation_key == token:
            matches = db.scalars(select(Match).where(Match.stage_id == key).order_by(Match.round, Match.code, Match.id))
            return {'data': {'id': key, 'matches': [serialize(match) for match in matches]}}
        fail('LOCKED','已有赛程，发布后不可重新生成；草稿请先明确作废',409)
    expect_version(s, payload.get('expected_version'))
    values=list(s.entries)
    if len(values)<2:fail('ENTRIES','请先配置阶段参赛队伍')
    active = set(db.scalars(select(Registration.id).where(
        Registration.competition_id == s.competition_id, Registration.active.is_(True))))
    if not set(values) <= active:
        fail('ENTRIES', '阶段参赛队伍已变化，请重新配置', 409)
    if s.config.get('draw')=='random':
        if 'random_seed' not in s.config:fail('SEED','随机分组需要保存抽签种子')
        random.Random(s.config['random_seed']).shuffle(values)
    nodes,edges=generate_graph(values,s.type,s.config)
    matches={}
    for n in nodes:
        m=Match(competition_id=s.competition_id,stage_id=s.id,**n)
        db.add(m);db.flush();matches[m.code]=m
    for e in edges:
        db.add(Advancement(competition_id=s.competition_id, source=matches[e['source']].id,target=matches[e['target']].id,outcome=e['outcome'],slot=e['slot']))
    s.status='preview';s.generation_key=token or uid()
    s.version += 1
    audit(db,'schedule.generate',s.id,{'config':s.config,'entries':values})
    return {'data':{'id':s.id,'matches':[serialize(m) for m in matches.values()]}}


def discard(key, db):
    s,_=lock_owner(db, Stage, key, '阶段不存在')
    if s.status!='preview':fail('LOCKED','只可作废未发布草稿',409)
    ids=list(db.scalars(select(Match.id).where(Match.stage_id==key)))
    db.execute(delete(Advancement).where(Advancement.source.in_(ids)))
    db.execute(delete(Match).where(Match.stage_id==key));s.status='draft';s.generation_key=None
    s.version += 1
    mark_public_change(db)
    audit(db,'schedule.discard',key,{})
    return {'data':True}


def publish_schedule(db, key, payload=None, token=None):
    s,c=lock_owner(db, Stage, key, '阶段不存在')
    payload = payload or {}
    def apply():
        return apply_schedule_publication(db, s, c, payload)
    return command(db, 'schedule.publish', key, token, payload, apply) if token is not None else apply()


def apply_schedule_publication(db, s, c, payload):
    key = s.id
    expect_version(s, payload.get('expected_version'))
    if s.status not in ('preview','published'):fail('SCHEDULE','请先生成草稿')
    if not c.published:fail('PUBLISH','请先发布赛事')
    if s.status=='published':return {'data':serialize(s)}
    if s.type=='group_single' and 'manual_groups' in s.config:
        generate_graph(list(s.entries),s.type,s.config)
    for m in db.scalars(select(Match).where(Match.stage_id == key).order_by(Match.id)):
        bind_rosters(db, m, {'a': m.a, 'b': m.b})
        m.published = True
    s.status = 'published'
    s.version += 1
    audit(db,'schedule.publish',s.id,{})
    return {'data':serialize(s)}


def matches(key, db):
    c=competition(db,key)
    return {'data':[serialize(m) for m in db.scalars(select(Match).where(Match.competition_id==c.id).order_by(Match.round,Match.code))]}


def arrange(key, payload, db):
    from datetime import datetime, timezone
    m,_=lock_owner(db, Match, key, '比赛不存在')
    expect_version(m, payload.get('expected_version'))
    before = m.scheduled_at, m.status
    if 'scheduled_at' in payload:
        scheduled=datetime.fromisoformat(payload['scheduled_at']) if payload['scheduled_at'] else None
        if scheduled and not scheduled.tzinfo:fail('TIMEZONE','时间必须包含时区')
        if scheduled:scheduled=scheduled.astimezone(timezone.utc)
        for other in db.scalars(select(Match).where(Match.competition_id==m.competition_id,Match.id!=key,Match.status.notin_(['cancelled','completed']))):
            if scheduled and other.scheduled_at and abs((scheduled.replace(tzinfo=None)-other.scheduled_at.replace(tzinfo=None)).total_seconds())<3600 and ({m.a,m.b}-{None})&({other.a,other.b}-{None}):fail('TIME_CONFLICT','同队比赛间隔不足一小时',409,{'match_id':other.id})
        m.scheduled_at=scheduled.astimezone(timezone.utc) if scheduled else None
    if 'status' in payload:
        if payload['status'] not in ('unscheduled','scheduled','ongoing','postponed','cancelled'):fail('STATUS','无效状态')
        if m.confirmed:fail('CONFIRMED','正式结果需通过修正流程修改',409)
        if payload['status']=='ongoing' and (not m.a or not m.b):fail('TBD','双方未确定')
        m.status=payload['status']
    if before != (m.scheduled_at, m.status):
        m.version += 1
    audit(db,'match.arrange',m.id,payload)
    return {'data':serialize(m)}


def get_match(key, db):
    m=db.get(Match,key)
    if not m:fail('NOT_FOUND','比赛不存在',404)
    return {'data':serialize(m)}
