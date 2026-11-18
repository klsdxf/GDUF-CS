import base64
import binascii
import io
import json
import os
from pathlib import Path
from urllib.parse import urlparse
from datetime import datetime, timezone
from PIL import Image, UnidentifiedImageError
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, tuple_
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from .schemas_public import Data
from .schemas_responses import AnnouncementRecord, StreamRecord
from .db import *
from .roster import competition, serialize, audit
from .schemas_admin import AnnouncementCreate, AnnouncementPatch, AuditItem, StreamCreate, StreamPatch
from .services.locking import expect_version, lock_owner
from .security import authenticated, authorized_form, upload_schema, fail

router=APIRouter(prefix='/api/v1/admin',dependencies=[Depends(authenticated)])

@router.get('/audit-logs')
def logs(action:str='',entity_id:str='',db:Session=db_transaction):
    q=select(Audit)
    if action:q=q.where(Audit.action.contains(action))
    if entity_id:q=q.where(Audit.entity_id==entity_id)
    return {'data':[serialize(x) for x in db.scalars(q.order_by(Audit.created_at.desc(), Audit.id.desc()).limit(500))]}


def cursor_for(stamp, identifier):
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return base64.urlsafe_b64encode(json.dumps([stamp.isoformat(), identifier]).encode()).decode().rstrip('=')


def read_cursor(cursor):
    try:
        raw = base64.urlsafe_b64decode(cursor + '=' * (-len(cursor) % 4))
        stamp, identifier = json.loads(raw)
        stamp = datetime.fromisoformat(stamp)
        if stamp.tzinfo is None or not isinstance(identifier, str) or not 1 <= len(identifier) <= 100:
            raise ValueError
        return stamp, identifier
    except (ValueError, TypeError, UnicodeDecodeError, binascii.Error):
        fail('CURSOR', '分页游标无效')


@router.get('/audit-logs/page')
def logs_page(action: str = Query('', max_length=100), entity_id: str = Query('', max_length=100),
              limit: int = Query(50, ge=1, le=100), cursor: str = Query('', max_length=300),
              db: Session = db_transaction):
    query = select(Audit)
    if action:
        query = query.where(Audit.action.contains(action, autoescape=True))
    if entity_id:
        query = query.where(Audit.entity_id == entity_id)
    if cursor:
        stamp, identifier = read_cursor(cursor)
        if db.get_bind().dialect.name == 'sqlite':
            stamp = stamp.astimezone(timezone.utc).replace(tzinfo=None)
        query = query.where(tuple_(Audit.created_at, Audit.id) < tuple_(stamp, identifier))
    rows = list(db.scalars(query.order_by(Audit.created_at.desc(), Audit.id.desc()).limit(limit + 1)))
    result = rows[:limit]
    return {'data': [AuditItem.model_validate(serialize(row)) for row in result],
            'meta': {'next_cursor': cursor_for(result[-1].created_at, result[-1].id) if len(rows) > limit else None}}

@router.get('/dashboard')
def dashboard(db:Session=db_transaction):
    return {'data': {'competitions': db.scalar(select(func.count()).select_from(Competition)),
                     'teams': db.scalar(select(func.count()).select_from(Registration).where(Registration.active.is_(True))),
                     'matches': db.scalar(select(func.count()).select_from(Match))}}

@router.get('/competitions/{key}/announcements', response_model=Data[list[AnnouncementRecord]])
def list_announcements(key:str,db:Session=db_transaction):
    c=competition(db,key)
    return {'data':[serialize(x) for x in db.scalars(select(Announcement).where(Announcement.competition_id==c.id))]}

def announcement_save(db,a,payload):
    if a.id:
        expect_version(a, payload.get('expected_version'))
        a.version += 1
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

@router.post('/announcements', response_model=Data[AnnouncementRecord])
def create_announcement(payload: AnnouncementCreate,db:Session=db_transaction):
    payload = payload.model_dump(mode='json', exclude_unset=True)
    c=competition(db,payload['competition_id'],True)
    return announcement_save(db,Announcement(competition_id=c.id,title='',body=''),payload)

@router.patch('/announcements/{key}', response_model=Data[AnnouncementRecord])
def edit_announcement(key:str,payload: AnnouncementPatch,db:Session=db_transaction):
    payload = payload.model_dump(mode='json', exclude_unset=True)
    a,_=lock_owner(db, Announcement, key, '公告不存在')
    return announcement_save(db,a,payload)

@router.get('/competitions/{key}/live', response_model=Data[list[StreamRecord]])
def live_list(key:str,db:Session=db_transaction):
    c=competition(db,key)
    return {'data':[serialize(x) for x in db.scalars(select(LiveStream).where(LiveStream.competition_id==c.id))]}

def live_save(db,l,payload):
    if l.id:
        expect_version(l, payload.get('expected_version'))
        l.version += 1
    for k in ('room_url','replay_url'):
        value=payload.get(k,getattr(l,k) or '')
        if value:
            parsed=urlparse(value)
            if parsed.scheme!='https' or not (parsed.hostname=='bilibili.com' or (parsed.hostname or '').endswith('.bilibili.com')):fail('URL','请填写 HTTPS B站链接')
        setattr(l,k,value)
    status=payload.get('status',l.status or 'offline')
    if status not in ('offline','live','replay'):fail('STATUS','无效直播状态')
    l.status=status
    if payload.get('match_id'):
        m=db.get(Match,payload['match_id'])
        if not m or m.competition_id!=l.competition_id:fail('MATCH','比赛不属于当前赛事')
        l.match_id=m.id
    elif 'match_id' in payload:
        l.match_id=None
    db.add(l);db.flush();audit(db,'live.save',l.id,{})
    return {'data':serialize(l)}

@router.post('/live-streams', response_model=Data[StreamRecord])
def create_live(payload: StreamCreate,db:Session=db_transaction):
    payload = payload.model_dump(mode='json', exclude_unset=True)
    c=competition(db,payload['competition_id'],True)
    return live_save(db,LiveStream(competition_id=c.id,room_url='',replay_url=''),payload)

@router.patch('/live-streams/{key}', response_model=Data[StreamRecord])
def edit_live(key:str,payload: StreamPatch,db:Session=db_transaction):
    payload = payload.model_dump(mode='json', exclude_unset=True)
    l,_=lock_owner(db, LiveStream, key, '直播不存在')
    return live_save(db,l,payload)

@router.post('/assets',openapi_extra=upload_schema())
async def asset(form=Depends(authorized_form, scope='function'),db:Session=db_transaction):
    file=form['file']
    raw=await file.read(2*1024*1024+1)
    if len(raw)>2*1024*1024:fail('FILE_SIZE','图片上限2MiB',413)
    return await run_in_threadpool(store_asset, db, raw)


def store_asset(db, raw):
    try:
        image=Image.open(io.BytesIO(raw))
        if image.format not in ('PNG','JPEG','WEBP') or max(image.size)>4096:fail('IMAGE','仅支持4096px以内 PNG/JPEG/WebP')
        image.load()
    except (UnidentifiedImageError,OSError):fail('IMAGE','图片无法读取')
    directory=Path(os.getenv('MEDIA_DIR','storage/media'));directory.mkdir(parents=True,exist_ok=True)
    name=uid()+'.webp';image.convert('RGBA').save(directory/name,'WEBP')
    audit(db,'asset.upload',name,{})
    return {'data':{'url':'/media/'+name}}
