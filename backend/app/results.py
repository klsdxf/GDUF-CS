from collections import defaultdict
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session
from .db import *
from .roster import competition, serialize, audit
from .security import authenticated, fail

router=APIRouter(prefix='/api/v1/admin',dependencies=[Depends(authenticated)])

def calculate(m, payload, c):
    if not m.a or not m.b:fail('TBD','双方未确定，不能录分')
    result_type=payload.get('result_type','normal')
    if result_type not in ('normal','forfeit','technical'):fail('RESULT_TYPE','无效结果类型')
    maps=payload.get('maps',[])
    if result_type!='normal':
        if payload.get('winner') not in (m.a,m.b) or not payload.get('reason'):fail('RESULT','异常结果需选择胜者并填写原因')
        if maps:fail('MAPS','弃权或技术判负不可伪造地图比分')
        return {'result_type':result_type,'maps':[],'winner':payload['winner'],'reason':payload['reason'],'wins_a':0,'wins_b':0,'complete':True}
    a=b=0;needed=m.best_of//2+1
    seen=set()
    for item in maps:
        if a==needed or b==needed:fail('MAPS','系列赛结束后不能继续追加地图')
        name=item.get('map_name')
        if name not in c.map_pool or name in seen:fail('MAP_POOL','地图不在赛事地图池中或重复')
        seen.add(name)
        x,y=item.get('score_a'),item.get('score_b')
        if type(x)!=int or type(y)!=int or min(x,y)<0 or x==y:fail('SCORE','回合数必须为非负整数且不能平局')
        if max(x,y)>13 and not item.get('overtime'):fail('OVERTIME','超过13回合请标记加时')
        if x>y:a+=1
        else:b+=1
    return {'result_type':'normal','maps':maps,'wins_a':a,'wins_b':b,'winner':m.a if a==needed else m.b if b==needed else None,'complete':a==needed or b==needed}

def downstream(db, m):
    found={};queue=[m.id]
    if m.group:
        for target in db.scalars(select(Match).where(Match.stage_id==m.stage_id,Match.group=='')):
            found[target.id]=target
    while queue:
        for edge in db.scalars(select(Advancement).where(Advancement.source==queue.pop(0))):
            if edge.target not in found:
                target=db.get(Match,edge.target);found[target.id]=target;queue.append(target.id)
    return list(found.values())

def propagate(db,m):
    for edge in db.scalars(select(Advancement).where(Advancement.source==m.id)):
        target=db.get(Match,edge.target)
        team=m.winner if edge.outcome=='winner' else (m.b if m.winner==m.a else m.a)
        setattr(target,edge.slot,team)
        versions=dict(target.rosters)
        if team:versions[team]=db.get(Registration,team).version
        target.rosters=versions
        if target.bracket=='reset':
            final=db.get(Match,edge.source)
            if final.winner==final.a:target.status='cancelled'

def match_locked(db,key):
    m=db.get(Match,key)
    if not m:fail('NOT_FOUND','比赛不存在',404)
    c=competition(db,m.competition_id,True)
    db.refresh(m)
    return m,c

@router.put('/matches/{key}/result')
def save_result(key:str,payload:dict,db:Session=Depends(db_session)):
    m,c=match_locked(db,key)
    if m.status=='cancelled':fail('CANCELLED','已取消比赛不能录分')
    if m.confirmed:fail('CONFIRMED','已确认比赛请通过修正流程操作',409)
    if payload.get('expected_version')!=m.version:fail('VERSION','成绩已变化，请刷新',409)
    m.draft_result=calculate(m,payload,c);m.version+=1
    audit(db,'result.draft',key,m.draft_result)
    return {'data':serialize(m)}

@router.post('/matches/{key}/result/confirm')
def confirm(key:str,payload:dict,db:Session=Depends(db_session)):
    m,c=match_locked(db,key)
    if m.confirmed and payload.get('expected_version')==m.version-1:return {'data':serialize(m)}
    if payload.get('expected_version')!=m.version:fail('VERSION','成绩已变化，请刷新',409)
    if not m.published or m.status=='cancelled':fail('MATCH','未发布或取消的比赛不能确认')
    r=calculate(m,m.draft_result,c)
    if not r['complete']:fail('INCOMPLETE','尚未达到 BO 所需胜场，不能确认')
    m.result=r;m.winner=r['winner'];m.confirmed=True;m.status='completed';m.version+=1
    propagate(db,m)
    audit(db,'result.confirm',key,{'result':r,'version':m.version})
    return {'data':serialize(m)}

@router.post('/matches/{key}/result/revise-preview')
def revise_preview(key:str,payload:dict,db:Session=Depends(db_session)):
    m,c=match_locked(db,key)
    affected=downstream(db,m)
    return {'data':{'result':calculate(m,payload,c),'affected':[serialize(x) for x in affected],'blocking':[x.id for x in affected if x.confirmed or x.status=='ongoing']}}

@router.post('/matches/{key}/result/revise')
def revise(key:str,payload:dict,db:Session=Depends(db_session)):
    m,c=match_locked(db,key)
    if not m.confirmed or payload.get('expected_version')!=m.version:fail('VERSION','比赛未确认或版本不符',409)
    if not payload.get('reason'):fail('REASON','修正必须填写原因')
    affected=downstream(db,m)
    blockers=[x.id for x in affected if x.confirmed or x.status=='ongoing']
    if blockers:fail('DOWNSTREAM','下游比赛已开始，请先显式处理',409,{'matches':blockers})
    result=calculate(m,payload,c)
    if not result['complete']:fail('INCOMPLETE','修正结果未达到终局')
    before=m.result
    for target in affected:
        incoming=list(db.scalars(select(Advancement).where(Advancement.target==target.id)))
        for edge in incoming:
            if edge.source==m.id or any(x.id==edge.source for x in affected):setattr(target,edge.slot,None)
        if m.group:
            for slot in ('a','b'):
                if getattr(target,'source_'+slot).startswith('group:'):setattr(target,slot,None)
        target.result={};target.draft_result={};target.winner=None;target.confirmed=False;target.version+=1
        if target.bracket=='reset':target.status='unscheduled'
    m.result=result;m.winner=result['winner'];m.version+=1
    if m.group:
        stage=db.get(Stage,m.stage_id)
        resolutions=dict(stage.config.get('ranking_resolution',{}));resolutions.pop(m.group,None)
        stage.config={**stage.config,'ranking_resolution':resolutions}
    propagate(db,m)
    audit(db,'result.revise',key,{'before':before,'after':result,'reason':payload['reason'],'version':m.version})
    return {'data':serialize(m)}

def standings(db,stage,group=None):
    matches=list(db.scalars(select(Match).where(Match.stage_id==stage.id)))
    groups=sorted({m.group for m in matches if m.group})
    output=[]
    for g in ([group] if group else groups or ['']):
        relevant=[m for m in matches if m.group==g and (bool(g) or m.bracket=='upper')]
        ids={t for m in relevant for t in (m.a,m.b) if t}
        rows={t:{'team_id':t,'name':db.get(Registration,t).name,'wins':0,'losses':0,'points':0,'map_diff':0,'round_diff':0,'head':0} for t in ids}
        for m in relevant:
            if not m.confirmed:continue
            loser=m.b if m.winner==m.a else m.a
            rows[m.winner]['wins']+=1;rows[m.winner]['points']+=3;rows[loser]['losses']+=1
            for item in m.result.get('maps',[]):
                x,y=item['score_a'],item['score_b'];sign=1 if x>y else -1
                rows[m.a]['map_diff']+=sign;rows[m.b]['map_diff']-=sign
                rows[m.a]['round_diff']+=x-y;rows[m.b]['round_diff']+=y-x
        # Mini table among teams tied on points; unresolved equal keys retain shared rank.
        for m in relevant:
            if m.confirmed and rows[m.a]['points']==rows[m.b]['points']:rows[m.winner]['head']+=3
        ordered=sorted(rows.values(),key=lambda r:(-r['points'],-r['head'],-r['map_diff'],-r['round_diff']))
        resolution=stage.config.get('ranking_resolution',{}).get(g,[])
        if resolution and set(resolution)==ids:ordered.sort(key=lambda r:resolution.index(r['team_id']))
        for i,row in enumerate(ordered):
            key=lambda r:(r['points'],r['head'],r['map_diff'],r['round_diff'])
            tied=[r for r in ordered if key(r)==key(row)]
            row['rank']=i+1 if resolution else min(ordered.index(r) for r in tied)+1
            row['unresolved']=len(tied)>1 and not resolution
            row['group']=g
        output.extend(ordered)
    return output

@router.put('/stages/{key}/ranking-resolution')
def resolve_ranking(key:str,payload:dict,db:Session=Depends(db_session)):
    s=db.get(Stage,key)
    if not s:fail('NOT_FOUND','阶段不存在',404)
    competition(db,s.competition_id,True)
    if not payload.get('reason'):fail('REASON','裁定必须填写原因')
    group=payload.get('group','');ranks=payload.get('teams',[])
    current=standings(db,s,group)
    if len(set(ranks))!=len(ranks) or set(ranks)!={r['team_id'] for r in current}:fail('RANKING','必须包含该组全部队伍且不重复')
    s.config={**s.config,'ranking_resolution':{**s.config.get('ranking_resolution',{}),group:ranks}}
    audit(db,'ranking.resolve',key,payload)
    return {'data':standings(db,s)}

@router.post('/stages/{key}/qualifications/confirm')
def qualify(key:str,db:Session=Depends(db_session)):
    s=db.get(Stage,key)
    if not s:fail('NOT_FOUND','阶段不存在',404)
    competition(db,s.competition_id,True)
    group_matches=list(db.scalars(select(Match).where(Match.stage_id==key,Match.group!='')))
    if not group_matches or any(not m.confirmed for m in group_matches):fail('INCOMPLETE','小组赛尚未全部确认')
    ranks=standings(db,s)
    if any(r['unresolved'] for r in ranks):fail('UNRESOLVED','排名有歧义，请先有理由裁定',409)
    for m in db.scalars(select(Match).where(Match.stage_id==key,Match.bracket=='playoff')):
        if m.confirmed or m.status=='ongoing':fail('LOCKED','淘汰赛已开始',409)
        for slot in ('a','b'):
            source=getattr(m,'source_'+slot)
            if source.startswith('group:'):
                _,g,rank=source.split(':');row=next(r for r in ranks if r['group']==g and r['rank']==int(rank))
                setattr(m,slot,row['team_id'])
    audit(db,'qualification.confirm',key,{})
    return {'data':True}
