import math
import random
from itertools import combinations
from fastapi import APIRouter, Depends
from sqlalchemy import select, delete
from sqlalchemy.orm import Session
from .db import *
from .roster import competition, serialize, audit
from .security import authenticated, fail

router=APIRouter(prefix='/api/v1/admin',dependencies=[Depends(authenticated)])

def seed_order(size):
    order=[1,2]
    while len(order)<size:
        total=len(order)*2+1
        order=[v for seed in order for v in (seed,total-seed)]
    return order

def generate_graph(entries,kind,config):
    nodes,edges=[],[]
    bo=int(config.get('best_of',1))
    if bo not in (1,3,5): fail('BO','BO仅允许1、3、5')
    def game(a,b,bracket,rnd,group=''):
        if a is None: return b,None
        if b is None: return a,None
        code=f'{bracket.upper()}{rnd}-{sum(n["bracket"]==bracket and n["round"]==rnd for n in nodes)+1}'
        node={'code':code,'a':None,'b':None,'source_a':'','source_b':'','round':rnd,'bracket':bracket,'group':group,'best_of':bo}
        for slot,ref in [('a',a),('b',b)]:
            if isinstance(ref,tuple):
                node['source_'+slot]=f'{ref[0]}:{ref[1]}'
                edges.append({'source':ref[0],'outcome':ref[1],'target':code,'slot':slot})
            elif isinstance(ref,str) and ref.startswith('group:'):
                node['source_'+slot]=ref
            else: node[slot]=ref
        nodes.append(node)
        return (code,'winner'),(code,'loser')
    def knockout(values,bracket='upper'):
        size=2**math.ceil(math.log2(max(2,len(values))))
        current=[values[s-1] if s<=len(values) else None for s in seed_order(size)]
        rounds=[]
        for rnd in range(1,int(math.log2(size))+1):
            winners,losers=[],[]
            for i in range(0,len(current),2):
                w,l=game(current[i],current[i+1],bracket,rnd)
                winners.append(w);losers.append(l)
            rounds.append(losers);current=winners
        return current[0],rounds
    if kind=='group_single':
        count=int(config.get('groups',4)); qualify=int(config.get('qualify',2))
        if count<1 or count>len(entries)//2 or qualify<1 or qualify>len(entries)//count:
            fail('GROUPS','分组数、晋级数不适用于当前参赛数量')
        groups=[entries[i::count] for i in range(count)]
        manual=config.get('manual_groups')
        if manual:
            if sorted(x for g in manual for x in g)!=sorted(entries): fail('GROUPS','手动分组须包含全部队伍且不得重复')
            groups=manual;count=len(groups)
        for idx,group in enumerate(groups):
            label=chr(65+idx)
            for rnd in range(1,3 if config.get('double_round') else 2):
                for a,b in combinations(group,2):
                    game(a,b,'group'+label,rnd,label)
        qualifiers=[f'group:{chr(65+g)}:{rank}' for rank in range(1,qualify+1) for g in range(count)]
        if config.get('qualifier_order'):
            if set(config['qualifier_order'])!=set(qualifiers) or len(config['qualifier_order'])!=len(qualifiers):fail('QUALIFIERS','跨组种子必须完整且不重复')
            qualifiers=config['qualifier_order']
        _,playoff_rounds=knockout(qualifiers,'playoff')
        if config.get('third_place') and len(playoff_rounds)>=2:game(*playoff_rounds[-2],'third',1)
    else:
        upper,rounds=knockout(entries)
        if config.get('third_place') and len(rounds)>=2:
            game(*rounds[-2], 'third',1)
        if kind=='double':
            if 'grand_final_reset' not in config: fail('RESET_RULE','双败总决赛必须明确是否重置')
            lower=rounds[0]
            lr=1
            lower=[game(lower[i],lower[i+1],'lower',lr)[0] for i in range(0,len(lower),2)] if len(lower)>1 else lower
            for drops in rounds[1:]:
                lr+=1
                drops=list(reversed(drops))
                lower=[game(lower[i],drops[i],'lower',lr)[0] for i in range(len(drops))]
                if len(lower)>1:
                    lr+=1
                    lower=[game(lower[i],lower[i+1],'lower',lr)[0] for i in range(0,len(lower),2)]
            final,_=game(upper,lower[0],'final',1)
            if config['grand_final_reset']:
                game((final[0],'winner'),(final[0],'loser'),'reset',1)
    return nodes,edges

@router.get('/competitions/{key}/stages')
def stages(key:str,db:Session=Depends(db_session)):
    c=competition(db,key)
    return {'data':[serialize(s) for s in db.scalars(select(Stage).where(Stage.competition_id==c.id))]}

@router.post('/stages')
def create_stage(payload:dict,db:Session=Depends(db_session)):
    c=competition(db,payload['competition_id'],True)
    if payload.get('type') not in ('single','group_single','double'): fail('TYPE','请选择三种赛制之一')
    s=Stage(competition_id=c.id,name=payload['name'],type=payload['type'],config=payload.get('config',{}))
    db.add(s);db.flush()
    audit(db,'stage.create',s.id,payload)
    return {'data':serialize(s)}

@router.patch('/stages/{key}')
def edit_stage(key:str,payload:dict,db:Session=Depends(db_session)):
    s=db.get(Stage,key)
    if not s: fail('NOT_FOUND','阶段不存在',404)
    competition(db,s.competition_id,True)
    if s.status!='draft': fail('LOCKED','请先作废草稿再修改',409)
    for k in ('name','config'): 
        if k in payload:setattr(s,k,payload[k])
    return {'data':serialize(s)}

@router.put('/stages/{key}/entries')
def entries(key:str,payload:dict,db:Session=Depends(db_session)):
    s=db.get(Stage,key)
    if not s: fail('NOT_FOUND','阶段不存在',404)
    competition(db,s.competition_id,True)
    if s.status!='draft':fail('LOCKED','已生成赛程，不能更换种子',409)
    valid=set(db.scalars(select(Registration.id).where(Registration.competition_id==s.competition_id,Registration.active==True)))
    values=payload.get('entries',[])
    if len(set(values))!=len(values) or not set(values)<=valid or not 2<=len(values)<=32:fail('ENTRIES','请选择2至32支有效队伍，种子不得重复')
    s.entries=values
    return {'data':serialize(s)}

@router.post('/stages/{key}/generate')
def generate(key:str,payload:dict,db:Session=Depends(db_session)):
    s=db.get(Stage,key)
    if not s:fail('NOT_FOUND','阶段不存在',404)
    competition(db,s.competition_id,True)
    if s.status!='draft':
        if s.generation_key==payload.get('idempotency_key'):return {'data':{'id':s.id}}
        fail('LOCKED','已有赛程，发布后不可重新生成；草稿请先明确作废',409)
    values=list(s.entries)
    if len(values)<2:fail('ENTRIES','请先配置阶段参赛队伍')
    if s.config.get('draw')=='random':
        if 'random_seed' not in s.config:fail('SEED','随机分组需要保存抽签种子')
        random.Random(s.config['random_seed']).shuffle(values)
    nodes,edges=generate_graph(values,s.type,s.config)
    matches={}
    for n in nodes:
        m=Match(competition_id=s.competition_id,stage_id=s.id,**n)
        db.add(m);db.flush();matches[m.code]=m
    for e in edges:
        db.add(Advancement(source=matches[e['source']].id,target=matches[e['target']].id,outcome=e['outcome'],slot=e['slot']))
    s.status='preview';s.generation_key=payload.get('idempotency_key') or uid()
    audit(db,'schedule.generate',s.id,{'config':s.config,'entries':values})
    return {'data':{'id':s.id,'matches':[serialize(m) for m in matches.values()]}}

@router.post('/stages/{key}/discard')
def discard(key:str,db:Session=Depends(db_session)):
    s=db.get(Stage,key)
    if not s:fail('NOT_FOUND','阶段不存在',404)
    competition(db,s.competition_id,True)
    if s.status!='preview':fail('LOCKED','只可作废未发布草稿',409)
    ids=list(db.scalars(select(Match.id).where(Match.stage_id==key)))
    db.execute(delete(Advancement).where(Advancement.source.in_(ids)))
    db.execute(delete(Match).where(Match.stage_id==key));s.status='draft';s.generation_key=None
    audit(db,'schedule.discard',key,{})
    return {'data':True}

@router.post('/schedule-generations/{key}/publish')
def publish(key:str,db:Session=Depends(db_session)):
    s=db.get(Stage,key)
    if not s:fail('NOT_FOUND','阶段不存在',404)
    c=competition(db,s.competition_id,True)
    if s.status not in ('preview','published'):fail('SCHEDULE','请先生成草稿')
    if not c.published:fail('PUBLISH','请先发布赛事')
    for m in db.scalars(select(Match).where(Match.stage_id==key)):
        m.published=True
        if m.a and m.b:
            m.rosters={t:db.get(Registration,t).version for t in (m.a,m.b)}
    s.status='published'
    audit(db,'schedule.publish',s.id,{})
    return {'data':serialize(s)}

@router.get('/competitions/{key}/matches')
def matches(key:str,db:Session=Depends(db_session)):
    c=competition(db,key)
    return {'data':[serialize(m) for m in db.scalars(select(Match).where(Match.competition_id==c.id).order_by(Match.round,Match.code))]}

@router.patch('/matches/{key}')
def arrange(key:str,payload:dict,db:Session=Depends(db_session)):
    from datetime import datetime, timezone
    m=db.get(Match,key)
    if not m:fail('NOT_FOUND','比赛不存在',404)
    competition(db,m.competition_id,True)
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
    audit(db,'match.arrange',m.id,payload)
    return {'data':serialize(m)}

@router.get('/matches/{key}')
def get_match(key:str,db:Session=Depends(db_session)):
    m=db.get(Match,key)
    if not m:fail('NOT_FOUND','比赛不存在',404)
    return {'data':serialize(m)}
