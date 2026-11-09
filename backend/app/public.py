from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from .db import *
from .roster import competition, serialize
from .results import standings
from .security import fail

router=APIRouter(prefix='/api/v1')

def public_c(db,key):
    c=competition(db,key)
    if not c.published:fail('NOT_FOUND','赛事尚未公布',404)
    return c

def team_dto(db,t,version=None):
    snapshot=db.get(RosterSnapshot,(t.id,version or t.version))
    return {'id':t.id,'competition_id':t.competition_id,'code':t.code,'name':snapshot.name if snapshot else t.name,'english_name':snapshot.english_name if snapshot else t.english_name,'emblem_text':snapshot.emblem_text if snapshot else t.emblem_text,'poster_title_lines':snapshot.poster_title_lines if snapshot else t.poster_title_lines,'description':snapshot.description if snapshot else t.description,'logo':snapshot.logo if snapshot else t.logo,'members':[{'nickname':m.nickname,'role':m.role,'captain':m.captain} for m in db.scalars(select(Member).where(Member.registration_id==t.id,Member.version==(version or t.version)))]}

def match_dto(db,m):
    out={k:getattr(m,k) for k in ('id','competition_id','stage_id','code','round','group','bracket','source_a','source_b','best_of','scheduled_at','status','confirmed','version')}
    out['result']=m.result if m.confirmed else {}
    out['teams']=[team_dto(db,db.get(Registration,t),m.rosters.get(t)) if t else None for t in (m.a,m.b)]
    return out

def c_dto(c):
    return {k:getattr(c,k) for k in ('id','slug','name','season','organizer','description','rules','map_pool','status','team_limit','is_default')}

@router.get('/competitions')
def competitions(db:Session=Depends(db_session)):
    return {'data':[c_dto(c) for c in db.scalars(select(Competition).where(Competition.published==True).order_by(Competition.is_default.desc(),Competition.season.desc()))]}

@router.get('/competitions/{key}')
def get_competition(key:str,db:Session=Depends(db_session)):
    return {'data':c_dto(public_c(db,key))}

@router.get('/competitions/{key}/teams')
def teams(key:str,db:Session=Depends(db_session)):
    c=public_c(db,key)
    return {'data':[team_dto(db,t) for t in db.scalars(select(Registration).where(Registration.competition_id==c.id,Registration.active==True))]}

@router.get('/competitions/{key}/teams/{team_id}')
def team(key:str,team_id:str,db:Session=Depends(db_session)):
    c=public_c(db,key);t=db.get(Registration,team_id)
    if not t or t.competition_id!=c.id or not t.active:fail('NOT_FOUND','战队不存在',404)
    return {'data':{**team_dto(db,t),'matches':[match_dto(db,m) for m in db.scalars(select(Match).where(Match.competition_id==c.id,Match.published==True,(Match.a==t.id)|(Match.b==t.id)))]}}

@router.get('/competitions/{key}/matches')
def matches(key:str,date:str|None=None,stage:str|None=None,status:str|None=None,db:Session=Depends(db_session)):
    c=public_c(db,key)
    q=select(Match).where(Match.competition_id==c.id,Match.published==True)
    if stage:q=q.where(Match.stage_id==stage)
    if status:q=q.where(Match.status==status)
    rows=list(db.scalars(q.order_by(Match.scheduled_at,Match.round,Match.code)))
    if date:rows=[m for m in rows if m.scheduled_at and m.scheduled_at.replace(tzinfo=timezone.utc).astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat()==date]
    return {'data':[match_dto(db,m) for m in rows]}

@router.get('/matches/{key}')
def match(key:str,db:Session=Depends(db_session)):
    m=db.get(Match,key)
    if not m or not m.published:fail('NOT_FOUND','比赛尚未公布',404)
    public_c(db,m.competition_id)
    return {'data':match_dto(db,m)}

@router.get('/competitions/{key}/stages')
def stages(key:str,db:Session=Depends(db_session)):
    c=public_c(db,key)
    return {'data':[{'id':s.id,'name':s.name,'type':s.type,'config':{k:v for k,v in s.config.items() if k in ('best_of','qualify','groups','grand_final_reset')}} for s in db.scalars(select(Stage).where(Stage.competition_id==c.id,Stage.status=='published'))]}

@router.get('/stages/{key}/standings')
def stage_standings(key:str,db:Session=Depends(db_session)):
    s=db.get(Stage,key)
    if not s or s.status!='published':fail('NOT_FOUND','阶段尚未公布',404)
    public_c(db,s.competition_id)
    return {'data':standings(db,s)}

@router.get('/stages/{key}/bracket')
def bracket(key:str,db:Session=Depends(db_session)):
    s=db.get(Stage,key)
    if not s or s.status!='published':fail('NOT_FOUND','阶段尚未公布',404)
    public_c(db,s.competition_id)
    ms=list(db.scalars(select(Match).where(Match.stage_id==key)))
    byes=[]
    for m in ms:
        if m.round>1 and not m.group:
            for slot in ('a','b'):
                team=getattr(m,slot);source=getattr(m,'source_'+slot)
                if (team and not source) or source.startswith('group:'):
                    byes.append({'name':db.get(Registration,team).name if team else None,'source':source})
    return {'data':{'matches':[match_dto(db,m) for m in ms],'edges':[serialize(e) for e in db.scalars(select(Advancement).where(Advancement.source.in_([m.id for m in ms])))],'bye_sources':byes}}

@router.get('/competitions/{key}/announcements')
def announcements(key:str,db:Session=Depends(db_session)):
    c=public_c(db,key)
    return {'data':[serialize(a) for a in db.scalars(select(Announcement).where(Announcement.competition_id==c.id,Announcement.published==True,Announcement.publish_at<=now()).order_by(Announcement.pinned.desc(),Announcement.publish_at.desc()))]}

@router.get('/announcements/{key}')
def announcement(key:str,db:Session=Depends(db_session)):
    a=db.get(Announcement,key)
    if not a or not a.published or a.publish_at.replace(tzinfo=timezone.utc)>now():fail('NOT_FOUND','公告尚未公布',404)
    public_c(db,a.competition_id)
    return {'data':serialize(a)}

@router.get('/competitions/{key}/live')
def live(key:str,db:Session=Depends(db_session)):
    c=public_c(db,key)
    return {'data':[serialize(s) for s in db.scalars(select(LiveStream).where(LiveStream.competition_id==c.id))]}

@router.get('/competitions/{key}/home')
def home(key:str,db:Session=Depends(db_session)):
    c=public_c(db,key)
    ms=list(db.scalars(select(Match).where(Match.competition_id==c.id,Match.published==True).order_by(Match.scheduled_at,Match.round)))
    focus=next((m for m in ms if m.id==c.focus_match_id),None) or next((m for m in ms if m.status=='ongoing'),None) or next((m for m in ms if not m.confirmed and m.status!='cancelled'),None)
    stages=list(db.scalars(select(Stage).where(Stage.competition_id==c.id,Stage.status=='published')))
    ts=list(db.scalars(select(Registration).where(Registration.competition_id==c.id,Registration.active==True)))
    return {'data':{'competition':c_dto(c),'team_count':len(ts),'focus':match_dto(db,focus) if focus else None,'matches':[match_dto(db,m) for m in ms],'standings':standings(db,stages[0]) if stages else [],'stages':[{'id':s.id,'name':s.name} for s in stages]}}
