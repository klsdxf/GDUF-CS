from sqlalchemy import select
from ..db import Advancement, Match, Registration, ResultRelease, Stage
from .roster_service import serialize, audit
from ..security import fail
from ..domain.score_rules import calculate
from .invalidation import invalidate_current
from ..services.locking import bind_rosters, expect_version, lock_owner, require_frozen_rosters
from ..services.operations import command


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
    edges = list(db.scalars(select(Advancement).where(Advancement.source == m.id)
                            .order_by(Advancement.target, Advancement.slot)))
    changes = {}
    for edge in edges:
        target=db.get(Match,edge.target)
        if not target or target.competition_id != m.competition_id:
            fail('CROSS_COMPETITION', '晋级目标必须属于本届赛事', 409)
        team=m.winner if edge.outcome=='winner' else (m.b if m.winner==m.a else m.a)
        changes.setdefault(target.id, (target, {'a': target.a, 'b': target.b}))[1][edge.slot] = team
    for target, slots in changes.values():
        if target.confirmed or target.status == 'ongoing':
            fail('DOWNSTREAM', '下游比赛已开始，请先显式处理', 409, {'matches': [target.id]})
        previous_version = target.version
        bind_rosters(db, target, slots)
        if target.bracket=='reset':
            if m.winner == m.a and target.status != 'cancelled':
                target.status = 'cancelled'
                if target.version == previous_version:
                    target.version += 1


def match_locked(db,key):
    return lock_owner(db, Match, key, '比赛不存在')


def save_result(key, payload, db):
    m,c=match_locked(db,key)
    if m.status=='cancelled':fail('CANCELLED','已取消比赛不能录分')
    if m.confirmed:fail('CONFIRMED','已确认比赛请通过修正流程操作',409)
    if payload.get('expected_version')!=m.version:fail('VERSION','成绩已变化，请刷新',409)
    m.draft_result=calculate(m,payload,c);m.version+=1
    audit(db,'result.draft',key,m.draft_result)
    return {'data':serialize(m)}


def confirm_result(db, key, payload, token=None):
    m,c=match_locked(db,key)

    def apply():
        if m.confirmed:
            fail('CONFIRMED', '已确认比赛请通过修正流程操作', 409)
        expect_version(m, payload['expected_version'])
        if not m.published or m.status == 'cancelled':
            fail('MATCH', '未发布或取消的比赛不能确认', 409)
        require_frozen_rosters(db, m)
        result = calculate(m, m.draft_result, c)
        if not result['complete']:
            fail('INCOMPLETE', '尚未达到 BO 所需胜场，不能确认')
        m.result = result
        m.winner = result['winner']
        m.confirmed = True
        m.status = 'completed'
        m.version += 1
        if m.group:
            db.get(Stage, m.stage_id).version += 1
        propagate(db, m)
        audit(db, 'result.confirm', key, {'result': result, 'version': m.version})
        return {'data': serialize(m)}

    if token is not None:
        return command(db, 'result.confirm', key, token, payload, apply)
    # Older clients identify a confirmation by the draft version.
    if m.confirmed and payload['expected_version'] != m.version - 1:
        fail('CONFIRMED', '已确认比赛请通过修正流程操作', 409)
    return command(db, 'result.confirm', key, f"confirm:{payload['expected_version']}", payload, apply)


def revise_preview(key, payload, db):
    m,c=match_locked(db,key)
    affected=downstream(db,m)
    return {'data':{'result':calculate(m,payload,c),'affected':[serialize(x) for x in affected],'blocking':[x.id for x in affected if x.confirmed or x.status=='ongoing'],'affected_releases':[r.id for r in db.scalars(select(ResultRelease).where(ResultRelease.competition_id==c.id,ResultRelease.status=='published'))]}}


def revise(key, payload, db):
    m,c=match_locked(db,key)
    if not m.confirmed or payload.get('expected_version')!=m.version:fail('VERSION','比赛未确认或版本不符',409)
    if not payload.get('reason'):fail('REASON','修正必须填写原因')
    require_frozen_rosters(db, m)
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
        target.rosters={team:version for team,version in target.rosters.items() if team in (target.a,target.b)}
        target.result={};target.draft_result={};target.winner=None;target.confirmed=False;target.version+=1
        if target.bracket=='reset':target.status='unscheduled'
    m.result=result;m.winner=result['winner'];m.version+=1
    if m.group:
        stage=db.get(Stage,m.stage_id)
        resolutions=dict(stage.config.get('ranking_resolution',{}));resolutions.pop(m.group,None)
        stage.config={**stage.config,'ranking_resolution':resolutions}
        stage.version += 1
    propagate(db,m)
    invalidate_current(db, c.id)
    audit(db,'result.revise',key,{'before':before,'after':result,'reason':payload['reason'],'version':m.version})
    return {'data':serialize(m)}


def standings(db,stage,group=None):
    matches=list(db.scalars(select(Match).where(Match.stage_id==stage.id)))
    groups=sorted({m.group for m in matches if m.group})
    output=[]
    ids = {t for m in matches for t in (m.a, m.b) if t}
    names = dict(db.execute(select(Registration.id, Registration.name).where(Registration.id.in_(ids))).all())
    for g in ([group] if group else groups or ['']):
        relevant=[m for m in matches if m.group==g and (bool(g) or m.bracket=='upper')]
        ids={t for m in relevant for t in (m.a,m.b) if t}
        rows={t:{'team_id':t,'name':names[t],'wins':0,'losses':0,'points':0,'map_diff':0,'round_diff':0,'head':0} for t in sorted(ids)}
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


def resolve_ranking(key, payload, db):
    s,_=lock_owner(db, Stage, key, '阶段不存在')
    expect_version(s, payload.get('expected_version'))
    if not payload.get('reason'):fail('REASON','裁定必须填写原因')
    group=payload.get('group','');ranks=payload.get('teams',[])
    current=standings(db,s,group)
    if len(set(ranks))!=len(ranks) or set(ranks)!={r['team_id'] for r in current}:fail('RANKING','必须包含该组全部队伍且不重复')
    by_id={r['team_id']:r for r in current}
    keys=[tuple(by_id[t][k] for k in ('points','head','map_diff','round_diff')) for t in ranks]
    if keys!=sorted(keys,reverse=True):fail('RANKING','只能对同分规则仍无法区分的队伍裁定，不能重排已确定名次')
    s.config={**s.config,'ranking_resolution':{**s.config.get('ranking_resolution',{}),group:ranks}}
    s.version += 1
    audit(db,'ranking.resolve',key,payload)
    return {'data':standings(db,s)}


def confirm_qualification(db, key, payload, token=None):
    s,_=lock_owner(db, Stage, key, '阶段不存在')

    def apply():
        expect_version(s, payload.get('expected_version'))
        return apply_qualification(db, s)

    return command(db, 'qualification.confirm', key, token, payload, apply) if token is not None else apply()


def apply_qualification(db, s):
    key = s.id
    group_matches=list(db.scalars(select(Match).where(Match.stage_id==key,Match.group!='')))
    if not group_matches or any(not m.confirmed for m in group_matches):fail('INCOMPLETE','小组赛尚未全部确认')
    ranks=standings(db,s)
    if any(r['unresolved'] for r in ranks):fail('UNRESOLVED','排名有歧义，请先有理由裁定',409)
    qualified={(row['group'],str(row['rank'])):row['team_id'] for row in ranks}
    changed = False
    for m in db.scalars(select(Match).where(Match.stage_id==key,Match.bracket=='playoff').order_by(Match.id)):
        if m.confirmed or m.status=='ongoing':fail('LOCKED','淘汰赛已开始',409)
        slots={'a':m.a,'b':m.b}
        for slot in ('a','b'):
            source=getattr(m,'source_'+slot)
            if source.startswith('group:'):
                team=qualified.get(tuple(source.split(':')[1:]))
                if team is None:
                    fail('QUALIFIERS','小组排名无法填满已配置的晋级位',409)
                slots[slot]=team
        changed |= bind_rosters(db, m, slots)
    if changed:
        s.version += 1
        invalidate_current(db, s.competition_id)
        audit(db,'qualification.confirm',key,{'version': s.version})
    return {'data':True}
