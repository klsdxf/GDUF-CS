"""Explicit, transactional import of the versioned public test dataset."""
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from .db import *
from .security import authenticated, fail
from .roster import serialize, save_roster
from . import roster, tournaments, results, final_results as fr, test_rankings

router=APIRouter(prefix='/api/v1/admin/test-data-imports',dependencies=[Depends(authenticated)])


class PreviewInput(BaseModel):
    package_key:str='public-test'
    package_version:str='1'


class CommitInput(BaseModel):
    content_sha256:str


def package(key,version):
    if (key,version)!=('public-test','1'):fail('PACKAGE','未知内置测试数据包',422)
    data=json.loads((Path(__file__).parents[1]/'fixtures/public-test-v1.json').read_text(encoding='utf-8'))
    return data,fr.digest_data(data)


def state(db):
    return fr.digest_data({cls.__tablename__:[serialize(x) for x in db.scalars(select(cls).order_by(cls.id))] for cls in (Competition,Registration,ResultPage,Sponsor,SeedBatch)})


def existing(db,data,sha):
    batch=db.scalar(select(SeedBatch).where(SeedBatch.package_key==data['package_key'],SeedBatch.package_version==data['package_version']))
    if batch and batch.content_sha256!=sha:fail('PACKAGE_CHANGED','同版本内容已变化，请升级数据包版本',409)
    return batch


def conflicts(db,data):
    found=[]
    for c in data['competitions']:
        if db.scalar(select(Competition.id).where(Competition.slug==c['slug'])):found.append('赛事路径已存在：'+c['slug'])
    for s in data['sponsors']:
        if db.scalar(select(Sponsor.id).where(Sponsor.name==s['name'])):found.append('品牌名称已存在：'+s['name'])
    return found


def summary(batch):
    return {'id':batch.id,'package_key':batch.package_key,'package_version':batch.package_version,'content_sha256':batch.content_sha256,'created_at':batch.created_at,'manifest':batch.manifest}


def import_package(db,data,sha,idempotency_key):
    batch=SeedBatch(package_key=data['package_key'],package_version=data['package_version'],content_sha256=sha,idempotency_key=idempotency_key,manifest={})
    db.add(batch);db.flush()
    entities=[]
    def track(kind,key,obj):
        db.flush()
        db.add(SeedEntity(batch_id=batch.id,entity_type=kind,source_key=key,entity_id=obj.id,imported_fingerprint=fr.digest_data(serialize(obj))))
        entities.append({'type':kind,'source_key':key,'id':obj.id})
    comps={}
    for item in data['competitions']:
        payload={k:v for k,v in item.items() if k not in ('source_key','status')}
        c=Competition(**payload,data_origin='test',seed_batch_id=batch.id,published=False,status=item['status'],is_default=False)
        db.add(c);db.flush();comps[item['source_key']]=c
    c=comps['autumn'];teams={}
    for item in data['teams']:
        tid=save_roster(db,c,[{k:v for k,v in item.items() if k!='source_key'}],'create')[0]
        t=db.get(Registration,tid);teams[item['source_key']]=t;track('team',item['source_key'],t)
        for index,member in enumerate(db.scalars(select(Member).where(Member.registration_id==t.id,Member.version==t.version))):track('member',item['source_key']+'-'+str(index),member)
    # Reuse the exact schedule and result services in this same DB transaction.
    for key,comp in comps.items():
        roster.publish_competition(comp.id,db)
        comp.status=next(x['status'] for x in data['competitions'] if x['source_key']==key)
    if not db.scalar(select(Competition.id).where(Competition.is_default==True)):
        c.is_default=True
    stage_id=tournaments.create_stage({'competition_id':c.id,'name':'小组赛与决赛','type':'group_single','config':{'best_of':3,'groups':1,'qualify':2}},db)['data']['id']
    tournaments.entries(stage_id,{'entries':[t.id for t in teams.values()]},db)
    tournaments.generate(stage_id,{'idempotency_key':batch.id},db)
    tournaments.publish(stage_id,db)
    track('stage','autumn-group-final',db.get(Stage,stage_id))
    for m in db.scalars(select(Match).where(Match.stage_id==stage_id,Match.group=='')):
        m.best_of=5
    for item in data['schedule']:
        a,b=teams[item['a']].id,teams[item['b']].id
        m=db.scalar(select(Match).where(Match.stage_id==stage_id,Match.a==a,Match.b==b))
        # The graph follows seed order; keep source-side score orientation explicit.
        if not m:
            m=db.scalar(select(Match).where(Match.stage_id==stage_id,Match.a==b,Match.b==a))
            m.a,m.b=a,b
        tournaments.arrange(m.id,{'scheduled_at':item['scheduled_at'],'status':'scheduled'},db)
        if item['maps']:
            results.save_result(m.id,{'expected_version':m.version,'maps':item['maps']},db)
            results.confirm(m.id,{'expected_version':m.version},db)
        if item['a']=='pp' and item['b']=='fs':c.focus_match_id=m.id
        track('match',item['source_key'],m)
    p=ResultPage(competition_id=c.id,result_kind='test',config={'ranking_method':'manual','seal_mode':'monogram','display_meta':{'edition_label':'2026 秋季赛','seal_edition_label':'FALL 2026','seal_serial':'001'}})
    db.add(p);db.flush()
    items=[]
    for item in data['test_matches']:
        mapped={k:v for k,v in item.items() if k not in ('a','b','winner','origin')}
        mapped.update(a_registration_id=teams[item['a']].id,b_registration_id=teams[item['b']].id,winner_registration_id=teams[item['winner']].id,a_display_version=1,b_display_version=1)
        items.append(mapped)
    test_rankings.save_matches(db,c,p,items)
    fr.replace_placements(db,c,p,test_rankings.ranking_items(db,c,p),calculated=True)
    partners={}
    for order,item in enumerate(data['sponsors']):
        sponsor=Sponsor(name=item['name'],data_origin='test',seed_batch_id=batch.id,data={'english_name':item['english_name'],'introduction':item.get('description',''),'builtin_mark_key':item.get('builtin_mark_key')})
        db.add(sponsor);db.flush();track('sponsor',item['id'],sponsor)
        partner=CompetitionPartner(competition_id=c.id,sponsor_id=sponsor.id,tier=item['tier'],published=True,data={'category':item['category'],'display_order':order})
        db.add(partner);db.flush();partners[item['id']]=partner;track('partner',item['id'],partner)
    prizes={}
    for order,item in enumerate(data['prizes']):
        z=Prize(competition_id=c.id,provider_partner_id=partners[item['provider_partner_id']].id,name=item['name'],data={**{k:item[k] for k in ('model_code','unit','category','builtin_illustration_key')},'display_order':order})
        db.add(z);db.flush();prizes[item['model_code']]=z;track('prize',item['model_code'],z)
    for r in fr.placements(db,p):
        for z in ([prizes[['H1','K75','M4'][r.rank_from-1]]] if r.rank_from<=3 else [])+[prizes['BADGE']]:
            a=PrizeAllocation(competition_id=c.id,placement_id=r.id,prize_id=z.id,quantity=5,data={'distribution':'per_recipient','per_recipient_quantity':1})
            db.add(a);track('allocation',str(r.rank_from)+'-'+z.data['model_code'],a)
    for item in data['news']:
        a=Announcement(competition_id=c.id,**{k:v for k,v in item.items() if k not in ('source_key','publish_at')},publish_at=datetime.fromisoformat(item['publish_at']).astimezone(timezone.utc),published=True)
        db.add(a);track('announcement',item['source_key'],a)
    for key,comp in comps.items():track('competition',key,comp)
    for m in test_rankings.matches(db,p):track('test_match',m.source_key,m)
    check=fr.validate(db,c,p)
    if check['blocking_errors']:fail('PUBLISH_INCOMPLETE','初始化数据未通过发布校验',422,check['blocking_errors'])
    released=fr.publish(c.id,fr.ResultPublishWrite(expected_version=p.version,expected_source_fingerprint=check['source_fingerprint'],reason='初始化四队测试排名'),batch.id,db)
    track('release','autumn-v1',db.get(ResultRelease,released['data']['id']))
    for r in fr.placements(db,p):track('placement',str(r.rank_from),r)
    track('result_page','autumn',p)
    batch.manifest={'entities':entities,'counts':{'competitions':3,'teams':4,'members':20,'announcements':3,'sponsors':5,'prizes':4},'sources':data['sources'],'content_changes':data['content_changes'],'supplemental_matches':[m for m in data['test_matches'] if m['origin']=='补充合成测试对局']}
    fr.audit(db,'test_data.import',batch.id,{'package':data['package_key'],'sha256':sha})
    db.flush()
    return batch


@router.post('/preview')
def preview(payload:PreviewInput,db:Session=Depends(db_session)):
    data,sha=package(payload.package_key,payload.package_version)
    batch=existing(db,data,sha)
    errors=[] if batch else conflicts(db,data)
    # Exercise the same business conversion without persisting any business rows.
    if not batch and not errors:
        transaction=db.begin_nested()
        try:import_package(db,data,sha,'preview-'+uid())
        finally:transaction.rollback()
    pv=SeedPreview(package_key=payload.package_key,package_version=payload.package_version,content_sha256=sha,state_fingerprint=state(db),expires_at=now()+timedelta(minutes=15))
    db.add(pv);db.flush()
    return {'data':{'id':pv.id,'content_sha256':sha,'expires_at':pv.expires_at,'already_imported':bool(batch),'batch_id':batch.id if batch else None,'conflicts':errors,'counts':{'competitions':3,'teams':4,'members':20,'announcements':3,'prizes':4,'sponsors':5},'content_changes':data['content_changes'],'supplemental_matches':[m for m in data['test_matches'] if m['origin']=='补充合成测试对局']}}


@router.post('/{preview_id}/commit')
def commit(preview_id:str,payload:CommitInput,idempotency_key:str=Header(),db:Session=Depends(db_session)):
    db.scalar(select(Admin).where(Admin.id==1).with_for_update())
    pv=db.get(SeedPreview,preview_id)
    if not pv:fail('NOT_FOUND','导入预览不存在',404)
    data,sha=package(pv.package_key,pv.package_version)
    old=db.scalar(select(SeedBatch).where(SeedBatch.idempotency_key==idempotency_key))
    if old:
        if old.content_sha256!=payload.content_sha256:fail('IDEMPOTENCY','幂等键已用于其他数据',409)
        return {'data':summary(old)}
    if sha!=payload.content_sha256 or sha!=pv.content_sha256:fail('PACKAGE_CHANGED','数据包已变化',409)
    batch=existing(db,data,sha)
    if batch:return {'data':summary(batch)}
    if pv.expires_at.replace(tzinfo=timezone.utc)<now() or state(db)!=pv.state_fingerprint:fail('IMPORT_STALE','预览过期或资料已变化，请重新预览',409)
    if conflicts(db,data):fail('IMPORT_CONFLICT','已有同路径赛事或同名品牌，不覆盖现有资料',409)
    return {'data':summary(import_package(db,data,sha,idempotency_key))}


@router.get('/{batch_id}')
def get_batch(batch_id:str,db:Session=Depends(db_session)):
    batch=db.get(SeedBatch,batch_id)
    if not batch:fail('NOT_FOUND','导入批次不存在',404)
    return {'data':summary(batch)}
