"""Independent backend result scenarios; never participate in the live schedule."""
from collections import Counter
from types import SimpleNamespace
from pydantic import BaseModel, Field
from typing import Literal
from sqlalchemy import select, delete
from .db import ResultTestMatch, Registration, RosterSnapshot, Member
from .security import fail
from .results import calculate


class ScenarioMatch(BaseModel):
    source_key: str = Field(min_length=1, max_length=100)
    a_registration_id: str
    b_registration_id: str
    winner_registration_id: str
    a_display_version: int = Field(ge=1)
    b_display_version: int = Field(ge=1)
    match_kind: Literal['semifinal','final','third_place']
    label: str = Field(min_length=1,max_length=100)
    best_of: Literal[1,3,5]
    wins_a: int = Field(ge=0)
    wins_b: int = Field(ge=0)
    maps: list[dict] | None = Field(default=None,max_length=5)
    champion_path_order: int | None = Field(default=None,ge=1)


class ScenarioWrite(BaseModel):
    expected_version: int = Field(ge=1)
    items: list[ScenarioMatch] = Field(max_length=64)


def require_test(c,p):
    if c.data_origin!='test' or p.result_kind!='test':
        fail('TEST_MODE_REQUIRED','仅测试赛事的测试排名可以维护独立对局',422)


def matches(db,p):
    return list(db.scalars(select(ResultTestMatch).where(ResultTestMatch.result_page_id==p.id).order_by(ResultTestMatch.source_key)))


def check_match(db,c,item):
    for side in ('a','b'):
        tid=item[side+'_registration_id'];version=item[side+'_display_version']
        team=db.get(Registration,tid)
        if not team or team.competition_id!=c.id or not team.active:
            fail('CROSS_COMPETITION','测试对局须引用本届有效队伍',422)
        if not db.get(RosterSnapshot,(tid,version)):
            fail('PUBLISH_INCOMPLETE','测试对局名单版本不存在',422)
    a,b=item['a_registration_id'],item['b_registration_id']
    needed=item['best_of']//2+1;x,y=item['wins_a'],item['wins_b']
    if a==b or not ((x==needed and y<needed) or (y==needed and x<needed)):
        fail('SCORE','双方或系列赛比分无效',422)
    winner=a if x>y else b
    if item['winner_registration_id']!=winner:
        fail('SCORE','胜者与系列赛比分不一致',422)
    if item.get('maps') is not None:
        result=calculate(SimpleNamespace(a=a,b=b,best_of=item['best_of']),{'maps':item['maps']},c)
        if result['winner']!=winner or (result['wins_a'],result['wins_b'])!=(x,y):
            fail('SCORE','逐图成绩与系列赛比分不一致',422)


def save_matches(db,c,p,items):
    require_test(c,p)
    keys=[m['source_key'] for m in items]
    orders=[m['champion_path_order'] for m in items if m.get('champion_path_order') is not None]
    if len(set(keys))!=len(keys) or len(set(orders))!=len(orders) or sum(m['match_kind']=='final' for m in items)>1:
        fail('SCENARIO','测试对局编号、路径顺序或决赛重复',422)
    for m in items:check_match(db,c,m)
    db.execute(delete(ResultTestMatch).where(ResultTestMatch.result_page_id==p.id))
    for m in items:
        db.add(ResultTestMatch(competition_id=c.id,result_page_id=p.id,**m,maps_status='provided' if m.get('maps') is not None else 'not_provided'))
    db.flush()


def outcome(db,c,p):
    """Validate the supported four-team bracket and derive all four placements."""
    require_test(c,p)
    ms=matches(db,p);semis=[m for m in ms if m.match_kind=='semifinal']
    finals=[m for m in ms if m.match_kind=='final'];thirds=[m for m in ms if m.match_kind=='third_place']
    if len(ms)!=4 or len(semis)!=2 or len(finals)!=1 or len(thirds)!=1:
        fail('SCENARIO','当前测试场景须包含两场半决赛、一场决赛和一场季军赛',422)
    from .roster import serialize
    for m in ms:check_match(db,c,serialize(m))
    active=set(db.scalars(select(Registration.id).where(Registration.competition_id==c.id,Registration.active==True)))
    entrants=[t for m in semis for t in (m.a_registration_id,m.b_registration_id)]
    if len(active)!=4 or set(entrants)!=active or any(n!=1 for n in Counter(entrants).values()):
        fail('SCENARIO','半决赛须完整覆盖本届四支有效队伍',422)
    loser=lambda m:m.b_registration_id if m.winner_registration_id==m.a_registration_id else m.a_registration_id
    final,third=finals[0],thirds[0]
    if {final.a_registration_id,final.b_registration_id}!={m.winner_registration_id for m in semis} or {third.a_registration_id,third.b_registration_id}!={loser(m) for m in semis}:
        fail('SCENARIO','决赛或季军赛与半决赛晋级不符',422)
    path=sorted([m for m in ms if m.champion_path_order is not None],key=lambda m:m.champion_path_order)
    semi=next(m for m in semis if m.winner_registration_id==final.winner_registration_id)
    if [m.id for m in path]!=[semi.id,final.id] or [m.champion_path_order for m in path]!=[1,2]:
        fail('SCENARIO','冠军之路须按半决赛、总决赛顺序排列',422)
    ranked=[final.winner_registration_id,loser(final),third.winner_registration_id,loser(third)]
    return ranked,final,third,path


def ranking_items(db,c,p):
    ranked,final,third,_=outcome(db,c,p)
    items=[]
    for rank,tid in enumerate(ranked,1):
        m=final if rank<=2 else third
        version=m.a_display_version if m.a_registration_id==tid else m.b_display_version
        count=len(list(db.scalars(select(Member).where(Member.registration_id==tid,Member.version==version,Member.role=='正式'))))
        items.append({'registration_id':tid,'rank_from':rank,'rank_to':rank,'team_display_version':version,'source_method':'calculated','eligibility_policy':'starters_only','recipient_count':count})
    return items


def match_dto(db,m):
    from .final_results import public_team
    teams=[public_team(db,db.get(Registration,getattr(m,side+'_registration_id')),getattr(m,side+'_display_version')) for side in ('a','b')]
    return {'id':m.id,'version':m.version,'label':m.label,'best_of':m.best_of,'teams':teams,'status':'completed',
            'a_team_id':m.a_registration_id,'b_team_id':m.b_registration_id,'winner_team_id':m.winner_registration_id,
            'result_type':'normal','wins_a':m.wins_a,'wins_b':m.wins_b,'maps':m.maps,'maps_status':m.maps_status,
            'source_kind':'result_test','detail_url':None}


def preview_matches(db,p):
    ms=matches(db,p)
    final=next((m for m in ms if m.match_kind=='final'),None)
    path=sorted([m for m in ms if m.champion_path_order is not None],key=lambda m:m.champion_path_order)
    return match_dto(db,final) if final else None,[match_dto(db,m) for m in path]
