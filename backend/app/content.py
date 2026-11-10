import io
import os
from pathlib import Path
from urllib.parse import urlparse
from datetime import datetime, timezone
from PIL import Image, UnidentifiedImageError
from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy import select
from sqlalchemy.orm import Session
from .db import *
from .roster import competition, serialize, audit
from .security import authenticated, fail

router=APIRouter(prefix='/api/v1/admin',dependencies=[Depends(authenticated)])

@router.get('/audit-logs')
def logs(action:str='',entity_id:str='',db:Session=Depends(db_session)):
    q=select(Audit)
    if action:q=q.where(Audit.action.contains(action))
    if entity_id:q=q.where(Audit.entity_id==entity_id)
    return {'data':[serialize(x) for x in db.scalars(q.order_by(Audit.created_at.desc()).limit(500))]}

@router.get('/dashboard')
def dashboard(db:Session=Depends(db_session)):
    return {'data':{'competitions':len(list(db.scalars(select(Competition.id)))),'teams':len(list(db.scalars(select(Registration.id).where(Registration.active==True)))),'matches':len(list(db.scalars(select(Match.id))))}}

@router.get('/competitions/{key}/announcements')
def list_announcements(key:str,db:Session=Depends(db_session)):
    c=competition(db,key)
    return {'data':[serialize(x) for x in db.scalars(select(Announcement).where(Announcement.competition_id==c.id))]}

def announcement_save(db,a,payload):
    if not payload.get('title',a.title) or not payload.get('body',a.body):fail('CONTENT','标题和正文必填')
    if len(payload.get('category_label',''))>100:fail('CONTENT','公告分类最多100字',422)
    for k in ('title','body','published','pinned','category_label','display_order'):
        if k in payload:setattr(a,k,payload[k])
    if payload.get('publish_at'):
        dt=datetime.fromisoformat(payload['publish_at'])
        if not dt.tzinfo:fail('TIMEZONE','发布时间需带时区')
        a.publish_at=dt.astimezone(timezone.utc)
    db.add(a);db.flush();audit(db,'announcement.save',a.id,{'title':a.title})
    return {'data':serialize(a)}

@router.post('/announcements')
def create_announcement(payload:dict,db:Session=Depends(db_session)):
    c=competition(db,payload['competition_id'])
    return announcement_save(db,Announcement(competition_id=c.id,title='',body=''),payload)

@router.patch('/announcements/{key}')
def edit_announcement(key:str,payload:dict,db:Session=Depends(db_session)):
    a=db.get(Announcement,key)
    if not a:fail('NOT_FOUND','公告不存在',404)
    return announcement_save(db,a,payload)

@router.get('/competitions/{key}/live')
def live_list(key:str,db:Session=Depends(db_session)):
    c=competition(db,key)
    return {'data':[serialize(x) for x in db.scalars(select(LiveStream).where(LiveStream.competition_id==c.id))]}

def live_save(db,l,payload):
    for k in ('room_url','replay_url'):
        value=payload.get(k,getattr(l,k) or '')
        if value:
            parsed=urlparse(value)
            if parsed.scheme!='https' or not (parsed.hostname=='bilibili.com' or (parsed.hostname or '').endswith('.bilibili.com')):fail('URL','请填写 HTTPS B站链接')
        setattr(l,k,value)
    if payload.get('status','offline') not in ('offline','live','replay'):fail('STATUS','无效直播状态')
    l.status=payload.get('status','offline')
    if payload.get('match_id'):
        m=db.get(Match,payload['match_id'])
        if not m or m.competition_id!=l.competition_id:fail('MATCH','比赛不属于当前赛事')
        l.match_id=m.id
    db.add(l);db.flush();audit(db,'live.save',l.id,{})
    return {'data':serialize(l)}

@router.post('/live-streams')
def create_live(payload:dict,db:Session=Depends(db_session)):
    c=competition(db,payload['competition_id'])
    return live_save(db,LiveStream(competition_id=c.id,room_url='',replay_url=''),payload)

@router.patch('/live-streams/{key}')
def edit_live(key:str,payload:dict,db:Session=Depends(db_session)):
    l=db.get(LiveStream,key)
    if not l:fail('NOT_FOUND','直播不存在',404)
    return live_save(db,l,payload)

@router.post('/assets')
async def asset(file:UploadFile=File(...),db:Session=Depends(db_session)):
    raw=await file.read(2*1024*1024+1)
    if len(raw)>2*1024*1024:fail('FILE_SIZE','图片上限2MiB',413)
    try:
        image=Image.open(io.BytesIO(raw))
        if image.format not in ('PNG','JPEG','WEBP') or max(image.size)>4096:fail('IMAGE','仅支持4096px以内 PNG/JPEG/WebP')
        image.load()
    except (UnidentifiedImageError,OSError):fail('IMAGE','图片无法读取')
    directory=Path(os.getenv('MEDIA_DIR','storage/media'));directory.mkdir(parents=True,exist_ok=True)
    name=uid()+'.webp';image.convert('RGBA').save(directory/name,'WEBP')
    audit(db,'asset.upload',name,{})
    return {'data':{'url':'/media/'+name}}
