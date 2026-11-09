import hashlib
import io
import re
import zipfile
from datetime import timedelta, timezone
from openpyxl import Workbook, load_workbook
from fastapi import APIRouter, Depends, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from sqlalchemy import select, delete
from sqlalchemy.orm import Session
from .db import *
from .security import authenticated, fail
from .schemas import CompetitionCreate

router = APIRouter(prefix='/api/v1/admin', dependencies=[Depends(authenticated)])

def serialize(obj):
    return {col.name: getattr(obj, col.name) for col in obj.__table__.columns}

def competition(db, key, lock=False):
    q = select(Competition).where((Competition.id == key) | (Competition.slug == key))
    if lock:
        q = q.with_for_update()
    value = db.scalar(q)
    if not value:
        fail('NOT_FOUND', '赛事不存在', 404)
    return value

def audit(db, action, entity, payload):
    db.add(Audit(action=action, entity_id=entity, payload=payload))

def private_team(db, team):
    return {**serialize(team), 'members': [serialize(x) for x in db.scalars(select(Member).where(Member.registration_id == team.id, Member.version == team.version))]}

def validate_roster(db, c, teams, mode, revision=False):
    errors, seen_ids, seen_names, seen_codes = [], set(), set(), set()
    existing = {x.code: x for x in db.scalars(select(Registration).where(Registration.competition_id == c.id, Registration.active == True))}
    updating = {x['code'] for x in teams}
    for claim in db.scalars(select(Claim).where(Claim.competition_id == c.id)):
        if not any(t.id == claim.registration_id and code in updating and mode == 'update' for code, t in existing.items()):
            seen_ids.add(claim.steam_id)
    for i, t in enumerate(teams):
        def err(message, column='队伍编号', sheet='队伍', row=None, code='INVALID_ROSTER'):
            errors.append({'sheet': sheet, 'row': row or t.get('_row', i + 2), 'column': column, 'team_code': t.get('code'), 'code': code, 'message': message})
        if not t.get('code') or len(t['code']) > 32 or t['code'] in seen_codes:
            err('队伍编号必填、最多32字且不能重复')
        seen_codes.add(t.get('code'))
        if t.get('code') in existing and mode == 'create':
            err('编号已存在，请选择更新模式', code='TEAM_EXISTS')
        if not t.get('name') or len(t['name']) > 100 or t['name'] in seen_names or any(v.name == t['name'] and k not in updating for k,v in existing.items()):
            err('队伍名称必填、最多100字且同届不能重名', '队伍名称')
        seen_names.add(t.get('name'))
        if not t.get('contact') or len(t['contact']) > 200:
            err('联系方式必填且最多200字', '队长联系方式')
        if len(t.get('english_name','')) > 120 or len(t.get('emblem_text','')) > 12 or len(t.get('poster_title_lines',[])) > 2 or any(not isinstance(x,str) or len(x)>120 for x in t.get('poster_title_lines',[])):
            err('英文队名最多120字，徽章缩写最多12字，海报标题最多两行')
        members = t.get('members', [])
        regular = [m for m in members if m.get('role') == '正式']
        captains = [m for m in members if m.get('captain')]
        if len(regular) != 5 or len(members) > 7 or len(captains) != 1 or captains[0].get('role') != '正式':
            err('每队必须五名正式、最多两名替补，且有一名正式队长')
        for m in members:
            if not isinstance(m.get('steam_id'), str) or not re.fullmatch(r'7656119\d{10}', m.get('steam_id', '')):
                err('SteamID64 必须为17位原始文本；数值单元格请重新填写', 'Steam ID', '成员', m.get('_row'))
            if m.get('steam_id') in seen_ids:
                err('该 Steam ID 在本赛事重复占用', 'Steam ID', '成员', m.get('_row'), 'MEMBER_CONFLICT')
            seen_ids.add(m.get('steam_id'))
            if not m.get('nickname') or len(m['nickname']) > 100 or m.get('role') not in ('正式', '替补'):
                err('昵称必填且最多100字，成员类型必须为正式或替补', '游戏昵称', '成员', m.get('_row'))
    if len(set(existing) | seen_codes) > c.team_limit:
        errors.append({'code': 'TEAM_LIMIT', 'message': '超过赛事参赛队伍上限'})
    if not revision and db.scalar(select(Stage.id).where(Stage.competition_id == c.id, Stage.status != 'draft')):
        errors.append({'code': 'ROSTER_LOCKED', 'message': '已生成赛程，普通名单操作已锁定'})
    return errors

def save_roster(db, c, teams, mode, revision=False):
    errors = validate_roster(db, c, teams, mode, revision)
    if errors:
        fail('INVALID_ROSTER', '名单校验未通过', details=errors)
    targets = []
    for t in teams:
        team = db.scalar(select(Registration).where(Registration.competition_id == c.id, Registration.code == t['code']))
        if not team:
            team = Registration(competition_id=c.id, code=t['code'], name=t['name'], contact=t['contact'])
            db.add(team)
            db.flush()
        else:
            db.execute(delete(Claim).where(Claim.registration_id == team.id))
            team.version += 1
        targets.append((team, t))
    db.flush()
    for team, t in targets:
        for field in ('name', 'contact', 'description', 'logo', 'english_name', 'emblem_text', 'poster_title_lines'):
            if field in t:
                setattr(team, field, t[field])
        team.active = True
        db.add(RosterSnapshot(registration_id=team.id,version=team.version,name=team.name,description=team.description,logo=team.logo,english_name=team.english_name,emblem_text=team.emblem_text,poster_title_lines=team.poster_title_lines))
        for m in t['members']:
            db.add(Member(registration_id=team.id, version=team.version, **{k:m[k] for k in ('nickname','steam_id','role','captain')}))
            db.add(Claim(competition_id=c.id, steam_id=m['steam_id'], registration_id=team.id))
    c.revision += 1
    audit(db, 'roster.save', c.id, {'codes': [t['code'] for t in teams], 'revision': c.revision})
    return [team.id for team, t in targets]

@router.post('/registrations/{key}/roster-revisions')
def revise_roster(key:str,payload:dict,db:Session=Depends(db_session)):
    t=db.get(Registration,key)
    if not t:fail('NOT_FOUND','队伍不存在',404)
    c=competition(db,t.competition_id,True)
    if not payload.get('reason'):fail('REASON','名单变更须填写原因')
    if payload.get('expected_version')!=t.version:fail('VERSION','名单版本已变更',409)
    payload['code']=t.code
    before=private_team(db,t)
    ids=save_roster(db,c,[payload],'update',True)
    audit(db,'roster.revise',t.id,{'before':before,'after':payload,'reason':payload['reason']})
    return {'data':{'ids':ids,'message':'既有比赛仍引用发布时的名单版本；变更仅影响后续新增比赛'}}

@router.get('/competitions')
def list_competitions(db: Session = Depends(db_session)):
    return {'data': [serialize(c) for c in db.scalars(select(Competition))]}

@router.post('/competitions')
def create_competition(payload: CompetitionCreate, db: Session = Depends(db_session)):
    payload=payload.model_dump()
    if not re.fullmatch('[a-z0-9-]{1,100}', payload.get('slug', '')) or not payload.get('name'):
        fail('COMPETITION', '名称必填，路径仅允许小写英文、数字和横线')
    c = Competition(**{k:v for k,v in payload.items() if k in ('slug','name','season','organizer','description','rules','map_pool','team_limit','config')})
    db.add(c); db.flush()
    audit(db, 'competition.create', c.id, {})
    return {'data': serialize(c)}

@router.patch('/competitions/{key}')
def edit_competition(key: str, payload: dict, db: Session = Depends(db_session)):
    c = competition(db, key, True)
    if payload.get('status',c.status) not in ('draft','roster_preparation','scheduling','ongoing','completed','archived'):fail('STATUS','无效赛事状态')
    if c.published and payload.get('status')=='draft':fail('STATUS','已发布赛事不能退回草稿；结束后可归档',409)
    if payload.get('team_limit',c.team_limit) not in range(2,33):fail('TEAM_LIMIT','队伍上限须在2至32之间')
    for k in ('name','season','organizer','description','rules','map_pool','team_limit','config','focus_match_id','status'):
        if k in payload:
            setattr(c,k,payload[k])
    if payload.get('is_default'):
        for other in db.scalars(select(Competition)):
            other.is_default = other.id == c.id
    elif 'is_default' in payload:c.is_default=False
    audit(db, 'competition.edit', c.id, payload)
    return {'data': serialize(c)}

@router.post('/competitions/{key}/publish')
def publish_competition(key: str, db: Session = Depends(db_session)):
    c = competition(db, key, True)
    if not c.rules or not c.map_pool:
        fail('CONFIG', '发布前请填写规则和地图池')
    c.published = True
    if c.status == 'draft': c.status = 'roster_preparation'
    audit(db, 'competition.publish', c.id, {})
    return {'data': serialize(c)}

@router.post('/competitions/{key}/archive')
def archive(key: str, db: Session = Depends(db_session)):
    c = competition(db, key, True); c.status = 'archived'
    audit(db, 'competition.archive', c.id, {})
    return {'data': serialize(c)}

@router.get('/competitions/{key}/registrations')
def registrations(key: str, db: Session = Depends(db_session)):
    c = competition(db,key)
    return {'data': [private_team(db,t) for t in db.scalars(select(Registration).where(Registration.competition_id == c.id, Registration.active == True))]}

@router.post('/competitions/{key}/registrations')
def add_team(key: str, payload: dict, db: Session = Depends(db_session)):
    c = competition(db,key,True)
    return {'data': save_roster(db,c,[payload],'create')}

@router.patch('/registrations/{key}')
def edit_team(key: str, payload: dict, db: Session = Depends(db_session)):
    team = db.get(Registration,key)
    if not team: fail('NOT_FOUND','队伍不存在',404)
    c = competition(db,team.competition_id,True)
    payload['code'] = team.code
    return {'data':save_roster(db,c,[payload],'update')}

@router.post('/registrations/{key}/withdraw')
def withdraw(key: str, db: Session = Depends(db_session)):
    t = db.get(Registration,key)
    if not t: fail('NOT_FOUND','队伍不存在',404)
    c = competition(db,t.competition_id,True)
    if db.scalar(select(Match.id).where((Match.a == key)|(Match.b == key))): fail('REFERENCED','队伍已关联赛程，不能撤销',409)
    t.active = False; c.revision += 1
    db.execute(delete(Claim).where(Claim.registration_id == key))
    audit(db,'roster.withdraw',key,{})
    return {'data':True}

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

@router.post('/competitions/{key}/imports/preview')
async def preview_import(key: str, file: UploadFile=File(...), mode: str=Form('create'), db: Session=Depends(db_session)):
    c=competition(db,key,True)
    if mode not in ('create','update'): fail('MODE','请选择新增或更新')
    if not file.filename.lower().endswith('.xlsx'): fail('FILE','仅支持 .xlsx')
    raw=await file.read(5*1024*1024+1)
    if len(raw)>5*1024*1024: fail('FILE_SIZE','文件上限5MiB',413)
    teams,errors=parse_excel(raw)
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
    batch=ImportBatch(competition_id=c.id,revision=c.revision,mode=mode,filename=file.filename,file_hash=hashlib.sha256(raw).hexdigest(),payload={'teams':teams,'errors':errors,'differences':differences,'summary':summary,'team_count':len(teams),'member_count':sum(len(t['members']) for t in teams)},expires_at=now()+timedelta(minutes=30))
    db.add(batch); db.flush()
    return {'data':serialize(batch)}

@router.post('/imports/{key}/commit')
def commit_import(key: str, payload: dict, db: Session=Depends(db_session)):
    b=db.get(ImportBatch,key)
    if not b: fail('NOT_FOUND','批次不存在',404)
    c=competition(db,b.competition_id,True)
    db.refresh(b)
    if b.status=='committed': return {'data':serialize(b)}
    if b.revision!=c.revision or b.expires_at.replace(tzinfo=timezone.utc)<now(): fail('ROSTER_VERSION_CONFLICT','名单已变化或预览已过期，请重新预览',409)
    if b.payload['errors']: fail('IMPORT_ERRORS','预览有错误，不能提交')
    if not payload.get('idempotency_key'): fail('IDEMPOTENCY','缺少幂等键')
    save_roster(db,c,b.payload['teams'],b.mode)
    b.status='committed'
    audit(db,'import.commit',b.id,{'hash':b.file_hash})
    return {'data':serialize(b)}

@router.get('/competitions/{key}/imports')
def imports(key:str,db:Session=Depends(db_session)):
    c=competition(db,key)
    return {'data':[serialize(b) for b in db.scalars(select(ImportBatch).where(ImportBatch.competition_id==c.id).order_by(ImportBatch.created_at.desc()))]}
