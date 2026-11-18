"""Final result drafts and immutable, public-only releases."""
import hashlib
import json
from collections import defaultdict
from copy import deepcopy
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select, delete, update, func, and_, or_
from ..db import *
from .roster_service import competition, serialize, audit
from ..schemas_admin import ExpectedVersion, PartnerCreate, PartnerPatch, PrizeCreate, PrizePatch, SponsorCreate, SponsorPatch, WithdrawResult
from ..security import fail
from . import invalidation  # register the compatibility listener
from ..services.operations import receipt, record, command
from ..schemas import ResultDraftWrite, ResultPlacementsWrite, ResultPathWrite, ResultAllocationsWrite, ResultPublishWrite
from ..public import c_dto
from ..queries.public_queries import match_dto, match_dtos
from .. import test_rankings


def digest_data(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False, default=str, separators=(',', ':')).encode()).hexdigest()


def rows(db, cls, cid):
    return list(db.scalars(select(cls).where(cls.competition_id == cid)))


def page(db, key, create=False):
    c = competition(db, key, True)
    p = db.scalar(select(ResultPage).where(ResultPage.competition_id == c.id).with_for_update()
                  .execution_options(populate_existing=True))
    if not p and create:
        p = ResultPage(competition_id=c.id, config={})
        db.add(p); db.flush()
    if not p: fail('NOT_FOUND', '请先创建结果工作稿', 404)
    return c, p


def bump(db, p, expected):
    old = p.version
    if old != expected: fail('VERSION', '工作稿已变化，请重新加载', 409)
    changed = db.execute(update(ResultPage).where(ResultPage.id == p.id, ResultPage.version == expected).values(version=old+1))
    if changed.rowcount != 1: fail('VERSION', '工作稿已变化，请重新加载', 409)
    db.refresh(p)


def same(db, cls, key, cid):
    value = db.get(cls, key)
    if not value or value.competition_id != cid: fail('CROSS_COMPETITION', '关联资料必须属于本届赛事', 422)
    return value


def placements(db, p):
    return list(db.scalars(select(ResultPlacement).where(ResultPlacement.result_page_id == p.id).order_by(ResultPlacement.rank_from,ResultPlacement.id)))


def sources(db, c, p):
    ps=placements(db,p)
    return {'competition': {k:getattr(c,k) for k in ('id','published','status','config','data_origin')},
            'matches': jsonable_encoder([serialize(m) for m in sorted(rows(db,Match,c.id),key=lambda x:x.id)]) if p.result_kind=='official' else [],
            'stages': [serialize(s) for s in sorted(rows(db,Stage,c.id),key=lambda x:x.id)] if p.result_kind=='official' else [],
            'test_matches':[serialize(m) for m in test_rankings.matches(db,p)] if p.result_kind=='test' else [],
            'teams':[{'id':t.id,'active':t.active} for t in sorted(rows(db,Registration,c.id),key=lambda x:x.id)],
            'snapshots':[serialize(db.get(RosterSnapshot,(r.registration_id,r.team_display_version))) for r in ps],
            'draft':{'version':p.version,'config':p.config,'result_kind':p.result_kind},
            'placements':[serialize(r) for r in ps],
            'allocations':[serialize(a) for a in db.scalars(select(PrizeAllocation).where(PrizeAllocation.competition_id==c.id).order_by(PrizeAllocation.id))],
            'partners':[serialize(x) for x in sorted(rows(db,CompetitionPartner,c.id),key=lambda x:x.id)],
            'sponsors':[serialize(db.get(Sponsor,x.sponsor_id)) for x in sorted(rows(db,CompetitionPartner,c.id),key=lambda x:x.id)],
            'prizes':[serialize(x) for x in sorted(rows(db,Prize,c.id),key=lambda x:x.id)]}


def public_team(db, t, version):
    s = db.get(RosterSnapshot,(t.id,version))
    if not s: fail('PUBLISH_INCOMPLETE','缺少所选队伍资料版本',422)
    return {'team_id':t.id,'id':t.id,'display_version':version,'name':s.name,'english_name':s.english_name,
            'emblem_text':s.emblem_text or t.code,'poster_title_lines':s.poster_title_lines or [s.english_name or s.name],
            'logo_url':s.logo or None}


def public_match(db, m, dto=None):
    if dto is None:
        dto=match_dto(db,m)
    return {**{k:dto[k] for k in ('id','version','best_of','teams','status')},'a_team_id':m.a,'b_team_id':m.b,'winner_team_id':m.winner,
            'result_type':m.result.get('result_type','normal'),'wins_a':m.result.get('wins_a'), 'wins_b':m.result.get('wins_b'),
            'maps':m.result.get('maps',[]),'reason':m.result.get('reason',''),'source_kind':'match','detail_url':'/matches/'+m.id}


PUBLIC_PARTNER_FIELDS = (
    'english_name', 'logo_url', 'category', 'introduction',
    'support_description', 'official_url', 'builtin_mark_key',
)


def partner_order(partner):
    order = partner.data.get('display_order')
    try:
        return int(order) if order is not None else 0
    except (ValueError, TypeError, OverflowError):
        return 0


def partner_payloads(db,c):
    partners=[]
    for x in sorted(rows(db,CompetitionPartner,c.id),key=lambda x:(partner_order(x),x.id)):
        s=db.get(Sponsor,x.sponsor_id)
        if x.published and s.active:
            partners.append({**s.data,**x.data,'id':x.id,'tier':x.tier,'name':s.name,'display_order':partner_order(x)})
    public_partners=[
        {'id':x['id'],'name':x['name'],'display_order':x['display_order'],
         **{k:x[k] for k in PUBLIC_PARTNER_FIELDS if k in x}}
        for x in partners
    ]
    return partners,public_partners


def published_prize_data(db,c):
    return [{'id':x.id,'name':x.name,'provider_partner_id':x.provider_partner_id,**x.data}
            for x in sorted(rows(db,Prize,c.id),key=lambda x:x.data.get('display_order',0)) if x.active]


def award_plan_data(page):
    plan=page.config.get('award_plan',{}) if page else {}
    if not plan:
        return {}
    return {'award_plan':plan,'hide_award_quantities':True,
            'has_third_place':bool(page.config.get('third_place_match_id'))}


def preview(db,c,p):
    ps=placements(db,p); out=[]
    for r in ps:
        t=same(db,Registration,r.registration_id,c.id)
        out.append({'id':r.id,'team_id':t.id,'registration_id':t.id,'rank_from':r.rank_from,'rank_to':r.rank_to,
                    'recipient_count':r.data.get('recipient_count',0),'source_method':r.data.get('source_method','calculated'),
                    'team':public_team(db,t,r.data.get('team_display_version',t.version))})
    partners,public_partners=partner_payloads(db,c)
    prizes=published_prize_data(db,c)
    by_placement = {r.id: r.registration_id for r in ps}
    allocation_rows = db.scalars(select(PrizeAllocation).where(PrizeAllocation.placement_id.in_(by_placement))
                                 .order_by(PrizeAllocation.placement_id, PrizeAllocation.id))
    allocations=[{'id':x.id,'placement_id':x.placement_id,'prize_id':x.prize_id,'quantity':x.quantity,
                  'registration_id':by_placement[x.placement_id],**x.data} for x in allocation_rows]
    path_rows = list(db.execute(select(ResultPathMatch, Match).join(Match, Match.id == ResultPathMatch.match_id)
                               .where(ResultPathMatch.result_page_id == p.id, Match.competition_id == c.id)
                               .order_by(ResultPathMatch.display_order)))
    path = [{**public_match(db, m, dto), 'label': item.stage_label}
            for (item, m), dto in zip(path_rows, match_dtos(db, [m for _, m in path_rows]), strict=True)]
    final=same(db,Match,p.config['final_match_id'],c.id) if p.config.get('final_match_id') else None
    final_dto=public_match(db,final) if final else None
    if p.result_kind=='test':final_dto,path=test_rankings.preview_matches(db,p)
    champion=next((r['team'] for r in out if r['rank_from']==r['rank_to']==1),None)
    totals={k:sum(a['quantity'] for a in allocations if any(z['id']==a['prize_id'] and z.get('category')==k for z in prizes)) for k in ('equipment','commemorative')}
    return {'schema_version':'1.0','competition':c_dto(c),'display':p.config.get('display_meta',{}),'champion':{**champion,'seal_mode':p.config.get('seal_mode','monogram')} if champion else None,
            'placements':out,'final_match':final_dto,'champion_path':path,'prizes':prizes,'allocations':allocations,
            'partners':public_partners,'presenting_partner':next((x for x in partners if x['tier']=='presenting'),None),
            'official_partners':[x for x in partners if x['tier']=='official'],'support_totals':totals,
            **award_plan_data(p)}


def final_match(db,c,p):
    s=same(db,Stage,p.config.get('final_stage_id'),c.id)
    ms=[m for m in rows(db,Match,c.id) if m.stage_id==s.id and not m.group and m.bracket!='third']
    outgoing=set(db.scalars(select(Advancement.source).where(
        Advancement.competition_id == c.id, Advancement.outcome == 'winner',
        Advancement.target.in_([m.id for m in ms]))))
    if s.type=='double':
        reset=next((m for m in ms if m.bracket=='reset'),None)
        final=next((m for m in ms if m.bracket=='final'),None)
        if reset and reset.status!='cancelled': final=reset
    else:
        terminals=[m for m in ms if m.id not in outgoing]
        final=terminals[0] if len(terminals)==1 else None
    if not final or not final.confirmed or not final.published or final.status!='completed' or not final.a or not final.b:
        fail('RESULT_NOT_FINAL','决定性终局比赛尚未正式确认',409)
    if p.config.get('final_match_id') and p.config['final_match_id']!=final.id:fail('RESULT_NOT_FINAL','所选比赛不是实际终局',409)
    return s,final,ms


def get_draft(key, db):
    c,p=page(db,key)
    return {'data':{**serialize(p),'placements':[{**serialize(r),**r.data} for r in placements(db,p)],'path':[serialize(x) for x in db.scalars(select(ResultPathMatch).where(ResultPathMatch.result_page_id==p.id))]}}


def save_draft(key, payload, db):
    payload=payload.model_dump(exclude_unset=True)
    return save_result_draft(key, payload, db)


def save_result_draft(key, payload, db):
    c,p=page(db,key,True)
    bump(db,p,payload.get('expected_version'))
    kind=payload.get('result_kind') or p.result_kind
    if kind=='test' and c.data_origin!='test':fail('TEST_MODE_REQUIRED','正式赛事不能创建测试排名',422)
    if kind!=p.result_kind and (p.current_release_id or placements(db,p) or test_rankings.matches(db,p)):
        fail('LOCKED','已有名次、对局或公开版本时不能直接切换排名类型',409)
    p.result_kind=kind
    allowed=('final_stage_id','final_match_id','third_place_match_id','ranking_method','rules_version','display_meta','seal_mode')
    changes = {k:v for k,v in payload.items() if k in allowed}
    if 'display_meta' in changes:
        changes['display_meta'] = {**p.config.get('display_meta', {}), **changes['display_meta']}
    p.config={**p.config, **changes}
    for field,cls in [('final_stage_id',Stage),('final_match_id',Match),('third_place_match_id',Match)]:
        if p.config.get(field):same(db,cls,p.config[field],c.id)
    audit(db,'final_results.draft',p.id,p.config)
    return {'data':serialize(p)}


def replace_placements(db,c,p,items,calculated=False):
    previous={r.registration_id:(r.rank_from,r.rank_to) for r in placements(db,p)}
    db.execute(delete(PrizeAllocation).where(PrizeAllocation.placement_id.in_([r.id for r in placements(db,p)])))
    db.execute(delete(ResultPlacement).where(ResultPlacement.result_page_id==p.id))
    for i,x in enumerate(items):
        t=same(db,Registration,x['registration_id'],c.id)
        if not calculated and previous.get(t.id)!=(x['rank_from'],x['rank_to']) and (x.get('source_method')!='ruling' or not x.get('ruling_reason')):fail('RANKING_AMBIGUOUS','变更计算名次须选择人工裁定并填写原因',422)
        if x.get('source_method')=='ruling' and not x.get('ruling_reason'):fail('RANKING_AMBIGUOUS','人工裁定须填写原因',422)
        v=x.get('team_display_version',t.version)
        if not db.get(RosterSnapshot,(t.id,v)):fail('PUBLISH_INCOMPLETE','队伍资料版本不存在',422)
        ms=[m for m in rows(db,Match,c.id) if m.confirmed and t.id in (m.a,m.b)]
        final=db.get(Match,p.config.get('final_match_id')) if p.config.get('final_match_id') else None
        deciding=final if final and t.id in (final.a,final.b) else next((m for m in ms if m.bracket=='third'),None)
        if not deciding:
            losses=[m for m in ms if m.winner!=t.id and m.bracket in ('upper','playoff','lower')]
            deciding=max(losses,key=lambda m:(m.bracket=='lower',m.round),default=None)
        match_version = deciding.rosters.get(t.id) if deciding and deciding.confirmed else t.version
        if match_version is None:
            fail('ROSTER_HISTORY_MISSING', '决定性比赛缺少历史名单版本', 409)
        if v!=match_version and not x.get('display_version_reason'):fail('REASON','使用不同于决定性比赛的品牌版本须说明原因',422)
        db.add(ResultPlacement(competition_id=c.id,team_display_version=v,result_page_id=p.id,registration_id=t.id,rank_from=x['rank_from'],rank_to=x['rank_to'],data={k:x[k] for k in ('team_display_version','source_method','ruling_reason','eligibility_policy','recipient_count','display_version_reason') if k in x}))
    db.flush()


def calculate_rankings(key, payload, db):
    payload = payload.model_dump(mode='json', exclude_unset=True)
    c,p=page(db,key);bump(db,p,payload.get('expected_version'))
    if p.result_kind=='test':
        replace_placements(db,c,p,test_rankings.ranking_items(db,c,p),calculated=True)
        audit(db,'final_results.test_calculate',p.id,{})
        return {'data':serialize(p)}
    s,f,ms=final_match(db,c,p)
    p.config={**p.config,'final_match_id':f.id,'ranking_method':s.type,'rules_version':'graph-v1'}
    loser=lambda m:m.b if m.winner==m.a else m.a
    groups=[[f.winner],[loser(f)]]; assigned=set(groups[0]+groups[1])
    third=next((m for m in rows(db,Match,c.id) if m.stage_id==s.id and m.bracket=='third'),None)
    if third:
        if not third.confirmed:fail('RESULT_NOT_FINAL','季军赛尚未确认',409)
        p.config={**p.config,'third_place_match_id':third.id}
        groups.extend([[third.winner],[loser(third)]]);assigned.update([third.winner,loser(third)])
    # Actual elimination depth, including lower bracket losses in double elimination.
    edges=list(db.scalars(select(Advancement).where(Advancement.competition_id == c.id)))
    graph={m.id:[e.target for e in edges if e.source==m.id and e.outcome=='winner' and any(n.id==e.target for n in ms)] for m in ms}
    def depth(mid):return 1+max((depth(t) for t in graph.get(mid,[])),default=0)
    buckets=defaultdict(list)
    for t in s.entries:
        if t in assigned:continue
        losses=[m for m in ms if m.confirmed and loser(m)==t]
        if s.type=='double':losses=[m for m in losses if m.bracket in ('lower','final','reset')]
        if losses:
            last=min(losses,key=lambda m:depth(m.id));buckets[depth(last.id)].append(t)
        else:buckets[999].append(t)
    groups.extend(buckets[k] for k in sorted(buckets))
    allteams=[t.id for t in rows(db,Registration,c.id) if t.active]
    missing=set(allteams)-{t for g in groups for t in g}
    if missing:groups.append(sorted(missing))
    items=[];rank=1
    for group in groups:
        for t in group:
            decisive=next((m for m in [f,third]+sorted(ms,key=lambda m:depth(m.id)) if m and t in (m.a,m.b) and m.confirmed),None)
            v=decisive.rosters.get(t) if decisive else db.get(Registration,t).version
            if v is None:
                fail('ROSTER_HISTORY_MISSING', '决定性比赛缺少历史名单版本', 409)
            items.append({'registration_id':t,'rank_from':rank,'rank_to':rank+len(group)-1,'team_display_version':v,'source_method':'calculated','eligibility_policy':'starters_only','recipient_count':len(list(db.scalars(select(Member).where(Member.registration_id==t,Member.version==v,Member.role=='正式'))))})
        rank+=len(group)
    replace_placements(db,c,p,items,calculated=True)
    db.execute(delete(ResultPathMatch).where(ResultPathMatch.result_page_id==p.id))
    for i,m in enumerate(sorted([m for m in ms if m.confirmed and m.winner==f.winner],key=lambda m:-depth(m.id))):db.add(ResultPathMatch(competition_id=c.id,result_page_id=p.id,match_id=m.id,display_order=i,stage_label=m.code))
    audit(db,'final_results.calculate',p.id,{'method':s.type})
    return get_draft(key,db)


def save_placements(key, payload, db):
    payload=payload.model_dump(exclude_unset=True)
    c,p=page(db,key);bump(db,p,payload.get('expected_version'));replace_placements(db,c,p,payload['items'])
    audit(db,'final_results.placements',p.id,{'count':len(payload['items'])})
    return get_draft(key,db)


def save_path(key, payload, db):
    payload=payload.model_dump(exclude_unset=True)
    c,p=page(db,key)
    if p.result_kind=='test':fail('TEST_MODE_REQUIRED','测试路径请在独立对局中维护',422)
    bump(db,p,payload.get('expected_version'))
    db.execute(delete(ResultPathMatch).where(ResultPathMatch.result_page_id==p.id))
    for i,x in enumerate(payload['items']):
        same(db,Match,x['match_id'],c.id)
        db.add(ResultPathMatch(competition_id=c.id,result_page_id=p.id,match_id=x['match_id'],display_order=i,stage_label=x.get('stage_label','')))
    audit(db,'final_results.path',p.id,{})
    return {'data':serialize(p)}


def get_preview(key, db):
    c,p=page(db,key);return {'data':preview(db,c,p)}


def validate(db,c,p):
    errors=[]
    def error(code,message):errors.append({'code':code,'message':message})
    f=None
    if p.result_kind=='test':
        if not c.published or c.data_origin!='test' or c.status not in ('ongoing','completed','archived'):
            error('TEST_MODE_REQUIRED','测试排名须属于已公开的测试赛事')
        try:
            expected=test_rankings.ranking_items(db,c,p)
            actual=placements(db,p)
            if {(r.registration_id,r.rank_from,r.rank_to,r.team_display_version) for r in actual}!={(r['registration_id'],r['rank_from'],r['rank_to'],r['team_display_version']) for r in expected}:
                error('SCENARIO','名次或资料版本与测试对局不一致，请重新计算')
        except Exception as exc:
            from fastapi import HTTPException
            if not isinstance(exc,HTTPException):raise
            error(exc.detail['code'],exc.detail['message'])
    else:
        if not c.published or c.status not in ('completed','archived'):error('RESULT_NOT_FINAL','赛事须公开并结束或归档')
        try:s,f,ms=final_match(db,c,p)
        except Exception as exc:
            from fastapi import HTTPException
            if not isinstance(exc,HTTPException):raise
            error('RESULT_NOT_FINAL','实际终局尚未确认')
    ps=placements(db,p);groups=defaultdict(list)
    for x in ps:groups[(x.rank_from,x.rank_to)].append(x)
    cursor=1
    for (a,b),g in sorted(groups.items()):
        if a!=cursor or len(g)!=b-a+1:error('INVALID_RANK_RANGE','名次区间须连续且人数与区间一致')
        cursor=b+1
    if {x.registration_id for x in ps}!={t.id for t in rows(db,Registration,c.id) if t.active}:error('INVALID_RANK_RANGE','须包含本届全部有效队伍')
    if f:
        required=[m for m in rows(db,Match,c.id) if m.stage_id==s.id and m.status!='cancelled']
        if any(not m.confirmed or not m.published for m in required):error('RESULT_NOT_FINAL','最终阶段仍有未确认或未公开比赛')
        third=next((m for m in required if m.bracket=='third'),None)
        if third and third.confirmed:
            for pos,tid in [(3,third.winner),(4,third.b if third.winner==third.a else third.a)]:
                if not any(x.registration_id==tid and x.rank_from==x.rank_to==pos for x in ps):error('RESULT_NOT_FINAL','季军赛名次与正式赛果不符')
        first=next((x.registration_id for x in ps if x.rank_from==x.rank_to==1),None)
        second=next((x.registration_id for x in ps if x.rank_from==x.rank_to==2),None)
        if first!=f.winner or second!=(f.b if f.winner==f.a else f.a):error('RESULT_NOT_FINAL','冠亚军必须与正式终局一致')
    dto=preview(db,c,p)
    if dto['champion'] and p.config.get('seal_mode')=='team_logo' and not dto['champion']['logo_url']:error('PUBLISH_INCOMPLETE','队标模式须上传冠军队标')
    if not dto['champion']:error('PUBLISH_INCOMPLETE','缺少冠军')
    for x in ps:
        t=db.get(Registration,x.registration_id);v=x.data.get('team_display_version',t.version)
        count=len(list(db.scalars(select(Member).where(Member.registration_id==t.id,Member.version==v))))
        policy=x.data.get('eligibility_policy','starters_only')
        if policy=='starters_only':count=len(list(db.scalars(select(Member).where(Member.registration_id==t.id,Member.version==v,Member.role=='正式'))))
        if policy=='explicit_count':
            if not x.data.get('ruling_reason'):error('AWARD_QUANTITY','自定领取人数须有理由')
        elif x.data.get('recipient_count')!=count:error('AWARD_QUANTITY','领取人数与所选名单不符')
    for m in dto['champion_path'] if p.result_kind=='official' else []:
        if not f or m['winner_team_id']!=f.winner or not same(db,Match,m['id'],c.id).published:error('RESULT_NOT_FINAL','路径必须为冠军正式获胜比赛')
    public_partner_ids = {x['id'] for x in dto['partners']}
    prizes_by_id = {x['id']:x for x in dto['prizes']}
    for a in dto['allocations']:
        r=next(x for x in ps if x.id==a['placement_id'])
        if a.get('distribution')=='per_recipient' and a['quantity']!=r.data.get('recipient_count',0)*(a.get('per_recipient_quantity') or 0):error('AWARD_QUANTITY','按人分配数量不一致')
        z=prizes_by_id.get(a['prize_id'])
        if not z:error('AWARD_QUANTITY','分配引用已停用奖品')
        elif z['provider_partner_id'] is not None and z['provider_partner_id'] not in public_partner_ids:
            error('PUBLISH_INCOMPLETE',f"奖品「{z['name']}」的提供方尚未公开或已停用，请恢复公开或改为本届实际提供方")
    if dto['champion'] and c.config.get('require_prize_allocations',True):
        for r in dto['placements']:
            if r['rank_from']<=3 and not any(a['placement_id']==r['id'] for a in dto['allocations']):error('PUBLISH_INCOMPLETE','前三名奖品尚未分配')
    if f and s.type=='group_single':
        # Cross-group ordering requires a public rule or a reasoned ruling.
        if any(x.data.get('source_method')!='ruling' for x in ps if x.registration_id not in s.entries):error('RANKING_AMBIGUOUS','跨组淘汰队伍须裁定')
    return {'draft_version':p.version,'source_fingerprint':digest_data(sources(db,c,p)),'warnings':[],'blocking_errors':errors}


def check(key, payload, db):
    payload = payload.model_dump(mode='json', exclude_unset=True)
    c,p=page(db,key)
    if payload.get('expected_version')!=p.version:fail('VERSION','工作稿已变化',409)
    return {'data':validate(db,c,p)}


def publish(key, payload, idempotency_key, db):
    return publish_result(db, key, payload.model_dump(exclude_unset=True), idempotency_key)


def publish_result(db, key, payload, idempotency_key):
    c,p=page(db,key)
    identity, request_hash, previous = receipt(db, 'ranking.publish', p.id, idempotency_key, payload)
    if previous:
        return previous.response_body
    old=db.scalar(select(ResultRelease).where(ResultRelease.result_page_id==p.id,ResultRelease.idempotency_key==idempotency_key))
    if old:
        draft_version = old.source_dependencies.get('draft', {}).get('version')
        if (old.source_fingerprint != payload.get('expected_source_fingerprint') or old.reason != payload.get('reason')
                or (draft_version is not None and draft_version != payload.get('expected_version'))):
            fail('IDEMPOTENCY_CONFLICT','幂等键已用于其他输入',409)
        return {'data':serialize(old)}
    if payload.get('expected_version')!=p.version:fail('VERSION','工作稿已变化',409)
    for cls in ((Stage, Registration, Match) if p.result_kind=='official' else (Registration, ResultTestMatch))+(CompetitionPartner,Prize):
        list(db.scalars(select(cls).where(cls.competition_id==c.id).order_by(cls.id).with_for_update()
                        .execution_options(populate_existing=True)))
    sponsor_ids=[x.sponsor_id for x in rows(db,CompetitionPartner,c.id)]
    list(db.scalars(select(Sponsor).where(Sponsor.id.in_(sponsor_ids)).order_by(Sponsor.id).with_for_update()
                    .execution_options(populate_existing=True)))
    v=validate(db,c,p)
    if v['source_fingerprint']!=payload.get('expected_source_fingerprint'):fail('SOURCE_CHANGED','源比赛或资料已变化，请重新校验',409)
    if v['blocking_errors']:fail('PUBLISH_INCOMPLETE','发布校验未通过',422,v['blocking_errors'])
    if not payload.get('reason'):fail('REASON','发布须填写原因',422)
    number=(db.scalar(select(func.max(ResultRelease.release_number)).where(ResultRelease.result_page_id==p.id)) or 0)+1
    rid=uid();stamp=now();dto=preview(db,c,p);dto['release']={'id':rid,'number':number,'published_at':stamp.isoformat(),'kind':p.result_kind}
    if dto.get('hide_award_quantities'):
        for placement in dto['placements']:
            placement.pop('recipient_count',None)
        for allocation in dto['allocations']:
            allocation.pop('quantity',None)
            allocation.pop('per_recipient_quantity',None)
        dto['support_totals']={}
    r=ResultRelease(result_kind=p.result_kind,data_origin=c.data_origin,id=rid,result_page_id=p.id,competition_id=c.id,release_number=number,source_fingerprint=v['source_fingerprint'],source_dependencies=sources(db,c,p),public_snapshot=deepcopy(dto),content_sha256=digest_data(dto),reason=payload['reason'],idempotency_key=idempotency_key,published_at=stamp)
    db.add(r);db.flush();bump(db,p,p.version);p.current_release_id=r.id
    audit(db,'final_results.publish',r.id,{'reason':r.reason,'sha256':r.content_sha256})
    return record(db, identity, request_hash, {'data':serialize(r)})


def withdraw(key, payload, idempotency_key, db):
    payload = payload.model_dump(mode='json', exclude_unset=True)
    c,p=page(db,key)
    def apply():
        return withdraw_result(db, p, payload)
    return command(db, 'ranking.withdraw', p.id, idempotency_key, payload, apply) if idempotency_key else apply()


def withdraw_result(db, p, payload):
    bump(db,p,payload.get('expected_version'))
    if not payload.get('reason'):fail('REASON','撤回须填写原因',422)
    if p.current_release_id:
        r=db.get(ResultRelease,p.current_release_id);r.status='withdrawn';r.invalidation_reason=payload['reason'];p.current_release_id=None
        audit(db,'final_results.withdraw',r.id,payload)
    return {'data':serialize(p)}


def releases(key, db):
    c,p=page(db,key);return {'data':[serialize(r) for r in rows(db,ResultRelease,c.id)]}


SPONSOR_FIELDS=('english_name','display_code','logo_url','tagline','introduction','official_url','builtin_mark_key')


PARTNER_FIELDS=('category','display_order','support_description')


PRIZE_FIELDS=('category','model_code','unit','description','image_url','builtin_illustration_key','display_order')


def media_fields(payload):
    import re
    from urllib.parse import urlsplit
    for k in ('logo_url','image_url'):
        value=payload.get(k)
        if value and not re.fullmatch(r'/media/[A-Za-z0-9_-]+\.webp',value):fail('MEDIA','图片须先通过上传接口保存',422)
    if payload.get('official_url'):
        u=urlsplit(payload['official_url'])
        if u.scheme!='https' or not u.hostname or u.username:fail('URL','官网须使用 HTTPS',422)
    for k,valid in [('builtin_mark_key',('nexcore',)),('builtin_illustration_key',('headset','keyboard','mouse','taisu-mousepad','punishgear-mousepad','grip-tape'))]:
        if payload.get(k) and payload[k] not in valid:fail('ASSET','未知内置图形',422)


def entity_dto(x):return {**serialize(x),**x.data}


def sponsors(db):
    return {'data': [entity_dto(sponsor) for sponsor in db.scalars(select(Sponsor).order_by(Sponsor.name, Sponsor.id))]}



def create_sponsor(payload, db):
    payload = payload.model_dump(mode='json', exclude_unset=True)
    return insert_sponsor(payload, db)


def insert_sponsor(payload, db):
    media_fields(payload);s=Sponsor(name=payload['name'],data_origin='test' if payload.get('data_origin')=='test' else 'regular',active=payload.get('active',True),data={k:payload[k] for k in SPONSOR_FIELDS if k in payload});db.add(s);db.flush();audit(db,'sponsor.create',s.id,{})
    return {'data':entity_dto(s)}


def edit_sponsor(key, payload, db):
    payload = payload.model_dump(mode='json', exclude_unset=True)
    return update_sponsor(key, payload, db)


def update_sponsor(key, payload, db):
    s=db.get(Sponsor,key)
    if not s:fail('NOT_FOUND','品牌不存在',404)
    if s.version!=payload.get('expected_version'):fail('VERSION','品牌版本已变化',409)
    changed=db.execute(update(Sponsor).where(Sponsor.id==key,Sponsor.version==payload['expected_version']).values(version=s.version+1))
    if changed.rowcount!=1:fail('VERSION','品牌版本已变化',409)
    db.refresh(s)
    media_fields(payload);s.name=payload.get('name',s.name);s.active=payload.get('active',s.active);s.data={**s.data,**{k:payload[k] for k in SPONSOR_FIELDS if k in payload}};audit(db,'sponsor.edit',s.id,{})
    return {'data':entity_dto(s)}


def partners(key, db):
    c=competition(db,key)
    return {'data':[{**entity_dto(x),'display_order':partner_order(x)}
                    for x in sorted(rows(db,CompetitionPartner,c.id),key=lambda x:(partner_order(x),x.id))]}


def prizes(key, db):
    c=competition(db,key);return {'data':[entity_dto(x) for x in rows(db,Prize,c.id)]}


def save_entity(db,c,p,payload,cls,obj=None):
    bump(db,p,payload.get('expected_version'));media_fields(payload)
    if cls==CompetitionPartner:
        sponsor_id = payload.get('sponsor_id', obj.sponsor_id if obj else None)
        if not sponsor_id or not db.get(Sponsor, sponsor_id):
            fail('NOT_FOUND','品牌不存在',404)
        if obj and sponsor_id != obj.sponsor_id:
            fail('SPONSOR_LINK','更换品牌需要新建合作关系',409)
        tier=payload.get('tier',obj.tier if obj else 'official')
        if tier not in ('presenting','official'):fail('TIER','无效合作级别',422)
        order=payload.get('display_order',partner_order(obj) if obj else 0)
        if order is None:order=0
        if type(order) is not int:fail('DISPLAY_ORDER','展示顺序须为整数',422)
        payload={**payload,'display_order':order}
        if obj is None:obj=cls(competition_id=c.id,sponsor_id=payload['sponsor_id'])
        obj.tier=tier;obj.published=payload.get('published',obj.published if obj.id else False);fields=PARTNER_FIELDS
    else:
        provider_id=payload.get('provider_partner_id',obj.provider_partner_id if obj else None)
        if provider_id is not None:
            same(db,CompetitionPartner,provider_id,c.id)
        if payload.get('category', obj.data.get('category') if obj else None) not in ('equipment','commemorative'):
            fail('CATEGORY','请选择奖品类别',422)
        if obj is None:obj=cls(competition_id=c.id,provider_partner_id=provider_id,name=payload['name'])
        obj.provider_partner_id = provider_id
        obj.name = payload.get('name', obj.name)
        obj.active = payload.get('active', obj.active if obj.id else True)
        fields = PRIZE_FIELDS
    obj.data={**(obj.data or {}), **{k:payload[k] for k in fields if k in payload}}
    if obj.id:obj.version+=1
    db.add(obj);db.flush();audit(db,'final_results.asset',obj.id,{'type':cls.__tablename__})
    return {'data':entity_dto(obj)}


def add_partner(key, payload, db):
    payload = payload.model_dump(mode='json', exclude_unset=True)
    c,p=page(db,key);return save_entity(db,c,p,payload,CompetitionPartner)


def add_prize(key, payload, db):
    payload = payload.model_dump(mode='json', exclude_unset=True)
    c,p=page(db,key);return save_entity(db,c,p,payload,Prize)


def edit_partner(key, payload, db):
    payload = payload.model_dump(mode='json', exclude_unset=True)
    x=db.get(CompetitionPartner,key)
    if not x:fail('NOT_FOUND','合作项不存在',404)
    c,p=page(db,x.competition_id)
    db.refresh(x)
    return save_entity(db,c,p,payload,CompetitionPartner,x)


def edit_prize(key, payload, db):
    payload = payload.model_dump(mode='json', exclude_unset=True)
    x=db.get(Prize,key)
    if not x:fail('NOT_FOUND','奖品不存在',404)
    c,p=page(db,x.competition_id)
    db.refresh(x)
    return save_entity(db,c,p,payload,Prize,x)


def save_allocations(key, payload, db):
    payload=payload.model_dump(exclude_unset=True)
    c,p=page(db,key);bump(db,p,payload.get('expected_version'));ps={r.id:r for r in placements(db,p)}
    db.execute(delete(PrizeAllocation).where(PrizeAllocation.placement_id.in_(ps)))
    for a in payload['items']:
        same(db,Prize,a['prize_id'],c.id)
        if a['placement_id'] not in ps:fail('CROSS_COMPETITION','获奖名次必须属于本届',422)
        if a.get('distribution') not in ('per_team','per_recipient'):fail('AWARD_QUANTITY','请选择分配方式',422)
        db.add(PrizeAllocation(competition_id=c.id,placement_id=a['placement_id'],prize_id=a['prize_id'],quantity=a['quantity'],data={k:a[k] for k in ('distribution','per_recipient_quantity','display_order') if k in a}))
    audit(db,'final_results.allocations',p.id,{'count':len(payload['items'])});return {'data':serialize(p)}


def visible(db, competition_id=None, limit=None):
    eligibility=or_(and_(ResultRelease.result_kind=='official',Competition.status.in_(['completed','archived'])),and_(ResultRelease.result_kind=='test',Competition.data_origin=='test',Competition.status.in_(['ongoing','completed','archived'])))
    query = (select(ResultRelease).join(ResultPage, ResultPage.current_release_id == ResultRelease.id)
             .join(Competition, Competition.id == ResultRelease.competition_id)
             .where(ResultRelease.status == 'published', Competition.published.is_(True), eligibility)
             .order_by(ResultRelease.published_at.desc(), ResultRelease.id.desc()))
    if competition_id is not None:
        query = query.where(ResultRelease.competition_id == competition_id)
    return list(db.scalars(query.limit(limit)))


def pending_result(db,competition):
    if competition and competition.published and competition.config.get('show_pending_results'):
        _,partners=partner_payloads(db,competition)
        result={'pending':True,'competition':c_dto(competition),'partners':partners}
        page=db.scalar(select(ResultPage).where(ResultPage.competition_id==competition.id))
        if page and page.config.get('award_plan'):
            prizes=published_prize_data(db,competition)
            plan=award_plan_data(page)
            announced={item for prize_ids in plan['award_plan'].values() for item in prize_ids}
            result.update(plan,prizes=[prize for prize in prizes if prize['id'] in announced])
        return result
    return None


def latest(db):
    current=db.scalar(select(Competition).where(Competition.is_default==True,Competition.published==True))
    if current and current.config.get('show_pending_results'):
        releases = visible(db, current.id, limit=1)
        return {'data': releases[0].public_snapshot if releases else pending_result(db, current)}
    releases = visible(db, limit=1)
    return {'data':releases[0].public_snapshot if releases else None}


def editions(db):
    return {'data':[{**r.public_snapshot['competition'],'release_id':r.id,'published_at':r.published_at} for r in visible(db)]}


def public_result(key, db):
    c=competition(db,key)
    r=next(iter(visible(db, c.id, limit=1)),None)
    data=r.public_snapshot if r else pending_result(db,c)
    if data is None:fail('NOT_FOUND','最终排名尚未公开或已失效',404)
    return {'data':data}


def get_test_matches(key, db):
    c,p=page(db,key);test_rankings.require_test(c,p)
    return {'data':{'version':p.version,'items':[serialize(m) for m in test_rankings.matches(db,p)]}}


def put_test_matches(key, payload, db):
    c,p=page(db,key);test_rankings.require_test(c,p)
    bump(db,p,payload.expected_version)
    test_rankings.save_matches(db,c,p,[m.model_dump() for m in payload.items])
    audit(db,'final_results.test_matches',p.id,{'count':len(payload.items)})
    return {'data':serialize(p)}
