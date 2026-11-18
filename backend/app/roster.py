import hashlib
import io
import re
import zipfile
from datetime import datetime, timedelta, timezone
from openpyxl import Workbook, load_workbook
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool
from sqlalchemy import select, delete, func
from sqlalchemy.orm import Session
from .schemas_public import Data
from .schemas_responses import CompetitionRecord
from .db import *
from .schemas_admin import CompetitionPatch, ImportCommit, RosterCreate, RosterEdit, RosterRevision
from .security import authenticated, authorized_form, upload_schema, fail
from .schemas import CompetitionCreate, CompetitionPresentation
from .services.locking import lock_owner
from .services.roster_service import (
    apply_competition_publication, apply_roster_revision, audit, commit_roster_import,
    competition, presentation_config, private_team, save_roster, serialize, update_competition,
    validate_roster, withdraw_registration,
)

router = APIRouter(prefix='/api/v1/admin', dependencies=[Depends(authenticated)])


@router.post('/registrations/{key}/roster-revisions')
def revise_roster(key:str,payload: RosterRevision,db:Session=db_transaction):
    payload = payload.model_dump(mode='json', exclude_unset=True)
    return apply_roster_revision(key, payload, db)


@router.get('/competitions', response_model=Data[list[CompetitionRecord]])
def list_competitions(data_origin:str='',db: Session = db_transaction):
    query=select(Competition)
    if data_origin:query=query.where(Competition.data_origin==data_origin)
    return {'data': [serialize(c) for c in db.scalars(query)]}

@router.post('/competitions', response_model=Data[CompetitionRecord])
def create_competition(payload: CompetitionCreate, db: Session = db_transaction):
    payload=payload.model_dump()
    payload['config']=presentation_config(payload['config'])
    if not re.fullmatch('[a-z0-9-]{1,100}', payload.get('slug', '')) or not payload.get('name'):
        fail('COMPETITION', '名称必填，路径仅允许小写英文、数字和横线')
    c = Competition(**{k:v for k,v in payload.items() if k in ('slug','name','season','organizer','description','rules','map_pool','team_limit','config')})
    db.add(c); db.flush()
    audit(db, 'competition.create', c.id, {})
    return {'data': serialize(c)}

@router.patch('/competitions/{key}', response_model=Data[CompetitionRecord])
def edit_competition(key: str, payload: CompetitionPatch, db: Session = db_transaction):
    payload = payload.model_dump(mode='json', exclude_unset=True)
    return update_competition(key, payload, db)


@router.post('/competitions/{key}/publish', response_model=Data[CompetitionRecord])
def publish_competition(key: str, db: Session = db_transaction):
    return apply_competition_publication(key, db)


@router.post('/competitions/{key}/archive', response_model=Data[CompetitionRecord])
def archive(key: str, db: Session = db_transaction):
    c = competition(db, key, True)
    if c.status == 'archived':
        return {'data': serialize(c)}
    c.status = 'archived'
    c.version += 1
    audit(db, 'competition.archive', c.id, {})
    return {'data': serialize(c)}

@router.get('/competitions/{key}/registrations')
def registrations(key: str, db: Session = db_transaction):
    c = competition(db,key)
    return {'data': [private_team(db,t) for t in db.scalars(select(Registration).where(Registration.competition_id == c.id, Registration.active == True))]}

@router.post('/competitions/{key}/registrations', response_model=Data[list[str]])
def add_team(key: str, payload: RosterCreate, db: Session = db_transaction):
    payload = payload.model_dump(mode='json', exclude_unset=True)
    c = competition(db,key,True)
    return {'data': save_roster(db,c,[payload],'create')}

@router.patch('/registrations/{key}', response_model=Data[list[str]])
def edit_team(key: str, payload: RosterEdit, db: Session = db_transaction):
    payload = payload.model_dump(mode='json', exclude_unset=True)
    team,c = lock_owner(db, Registration, key, '队伍不存在')
    if payload.get('expected_version', team.version) != team.version:
        fail('VERSION', '名单版本已变更', 409)
    payload['code'] = team.code
    return {'data':save_roster(db,c,[payload],'update')}

@router.post('/registrations/{key}/withdraw', response_model=Data[bool])
def withdraw(key: str, db: Session = db_transaction):
    return withdraw_registration(key, db)


@router.get('/imports/template')
def template():
    wb = Workbook(); ws = wb.active; ws.title = '队伍'
    ws.append(['队伍编号','队伍名称','队伍简介','队长联系方式'])
    ms = wb.create_sheet('成员'); ms.append(['队伍编号','游戏昵称','Steam ID','成员类型','是否队长'])
    meta = wb.create_sheet('说明'); meta.append(['模板版本','1']); meta.append(['规则','最多32队、224人、5MiB；每队5正式+至多2替补；Steam ID必须原始文本；上传仅预览'])
    for sheet in (ws,ms):
        sheet.freeze_panes='A2'
        for row in sheet.iter_rows(min_row=2,max_row=225,max_col=sheet.max_column):
            for cell in row: cell.number_format='@'
        for column in 'ABCDE': sheet.column_dimensions[column].width=25
    out=io.BytesIO(); wb.save(out); out.seek(0)
    return StreamingResponse(out,media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':'attachment; filename=roster-v1.xlsx'})

def parse_excel(raw):
    errors, teams = [], {}
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            if sum(i.file_size for i in z.infolist()) > 20*1024*1024 or any('vbaProject' in n for n in z.namelist()):
                fail('FILE','解压后超过20MiB或含宏')
        wb=load_workbook(io.BytesIO(raw),data_only=False,read_only=True,keep_links=False)
    except (zipfile.BadZipFile, KeyError, ValueError):
        fail('FILE','文件不是有效 xlsx 工作簿')
    mapping={'队伍':{'队伍编号':'code','队伍名称':'name','队伍简介':'description','队长联系方式':'contact'},'成员':{'队伍编号':'code','游戏昵称':'nickname','Steam ID':'steam_id','成员类型':'role','是否队长':'captain'}}
    for sheet, fields in mapping.items():
        if sheet not in wb.sheetnames: fail('SHEET','缺少工作表：'+sheet)
        ws=wb[sheet]
        header=[c.value for c in next(ws.iter_rows())]
        if not set(fields).issubset(header): fail('HEADERS','缺少列：'+','.join(set(fields)-set(header)))
        for row_num,row in enumerate(ws.iter_rows(min_row=2),2):
            if row_num > 226: fail('ROWS','工作表超过224条数据')
            if all(c.value is None for c in row): continue
            data={'_row':row_num}
            for col,key in fields.items():
                cell=row[header.index(col)]
                value=cell.value
                if cell.data_type in ('f','e') or (key=='steam_id' and not isinstance(value,str)):
                    errors.append({'sheet':sheet,'row':row_num,'column':col,'code':'CELL_TYPE','message':'不接受公式、错误或数值 Steam ID；请填写原始文本'})
                data[key]=str(value).strip() if value is not None else ''
            if sheet=='队伍':
                if data['code'] in teams: errors.append({'sheet':sheet,'row':row_num,'column':'队伍编号','code':'DUPLICATE','message':'编号重复'})
                teams[data['code']]={**data,'members':[]}
            else:
                if data['captain'] not in ('是','否'): errors.append({'sheet':sheet,'row':row_num,'column':'是否队长','code':'ENUM','message':'仅允许是或否'})
                data['captain']=data['captain']=='是'
                if data['code'] not in teams: errors.append({'sheet':sheet,'row':row_num,'column':'队伍编号','code':'REFERENCE','message':'成员引用不存在的队伍'})
                else: teams[data.pop('code')]['members'].append(data)
    wb.close()
    if not teams: errors.append({'code':'EMPTY','message':'没有队伍数据'})
    return list(teams.values()),errors

@router.post('/competitions/{key}/imports/preview',openapi_extra=upload_schema(with_mode=True))
async def preview_import(key: str, form=Depends(authorized_form, scope='function'), db: Session=db_transaction):
    file=form['file']
    mode=form.get('mode','create')
    if mode not in ('create','update'): fail('MODE','请选择新增或更新')
    if not (file.filename or '').lower().endswith('.xlsx'): fail('FILE','仅支持 .xlsx')
    raw=await file.read(5*1024*1024+1)
    if len(raw)>5*1024*1024: fail('FILE_SIZE','文件上限5MiB',413)
    teams,errors=await run_in_threadpool(parse_excel, raw)
    return await run_in_threadpool(save_import_preview, db, key, mode, file.filename, raw, teams, errors)


def save_import_preview(db, key, mode, filename, raw, teams, errors):
    c=competition(db,key,True)
    errors+=validate_roster(db,c,teams,mode)
    differences=[]
    summary={'new':0,'modified':0,'unchanged':0}
    for t in teams:
        old=db.scalar(select(Registration).where(Registration.competition_id==c.id,Registration.code==t['code']))
        before=private_team(db,old) if old else None
        def comparable(value):
            return {**{k:value.get(k,'') for k in ('code','name','description','contact')},'members':sorted([{k:m[k] for k in ('nickname','steam_id','role','captain')} for m in value['members']],key=lambda m:m['steam_id'])}
        change='new' if before is None else 'unchanged' if comparable(before)==comparable(t) else 'modified'
        summary[change]+=1
        differences.append({'code':t['code'],'change':change,'before':before,'after':t,'removed_members':[m for m in before['members'] if m['steam_id'] not in {n['steam_id'] for n in t['members']}] if before else []})
    batch=ImportBatch(competition_id=c.id,revision=c.revision,mode=mode,filename=filename,file_hash=hashlib.sha256(raw).hexdigest(),payload={'teams':teams,'errors':errors,'differences':differences,'summary':summary,'team_count':len(teams),'member_count':sum(len(t['members']) for t in teams)},expires_at=now()+timedelta(minutes=30))
    db.add(batch); db.flush()
    return {'data':serialize(batch)}

@router.post('/imports/{key}/commit')
def commit_import(key: str, payload: ImportCommit, db: Session=db_transaction):
    payload = payload.model_dump(mode='json', exclude_unset=True)
    return commit_roster_import(key, payload, db)


@router.get('/competitions/{key}/imports')
def imports(key:str,db:Session=db_transaction):
    c=competition(db,key)
    return {'data':[serialize(b) for b in db.scalars(select(ImportBatch).where(ImportBatch.competition_id==c.id).order_by(ImportBatch.created_at.desc()))]}
