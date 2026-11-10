from copy import deepcopy
import json
import pytest
from sqlalchemy import select
from .test_platform import client, call, setup_competition
from app.db import db_session, Competition, Registration, ResultRelease, ResultPage, Match, SeedBatch, SeedEntity, ResultTestMatch


def imported(client):
    preview=call(client,'/admin/test-data-imports/preview','post',{})
    assert not preview['conflicts']
    response=client.post('/api/v1/admin/test-data-imports/'+preview['id']+'/commit',json={'content_sha256':preview['content_sha256']},headers={'Idempotency-Key':preview['id']})
    assert response.status_code==200,response.text
    return preview,response.json()['data']


def publish(client,base):
    p=call(client,base+'/draft')
    v=call(client,base+'/validate','post',{'expected_version':p['version']})
    assert not v['blocking_errors'],v
    response=client.post('/api/v1'+base+'/publish',json={'expected_version':p['version'],'expected_source_fingerprint':v['source_fingerprint'],'reason':'测试排名更新'},headers={'Idempotency-Key':'republish-'+str(p['version'])})
    assert response.status_code==200,response.text
    return response.json()['data']


def test_import_persistent_four_teams_and_repeat_preserves_edits(client):
    pv,batch=imported(client)
    comps=call(client,'/admin/competitions')
    assert len(comps)==3 and all(c['data_origin']=='test' for c in comps)
    c=next(c for c in comps if c['slug']=='autumn')
    assert c['status']=='ongoing'
    teams=call(client,'/competitions/autumn/teams')
    assert len(teams)==4 and sum(len(t['members']) for t in teams)==20
    assert next(t for t in teams if t['code']=='PP')['name']=="Poppin'Party"
    public=call(client,'/results/latest')
    assert public['champion']['name']=="Poppin'Party" and len(public['placements'])==4
    assert public['release']['kind']=='test' and public['competition']['status']=='ongoing'
    assert len(public['champion_path'])==2
    assert all(m['source_kind']=='result_test' and m['detail_url'] is None for m in public['champion_path'])
    assert public['support_totals']=={'equipment':15,'commemorative':20}
    assert 'steam_id' not in json.dumps(public) and '内部测试占位' not in json.dumps(public)
    assert call(client,'/competitions/autumn/results')==public
    assert client.get('/internal/page-check',headers={'x-original-uri':'/results/autumn'}).status_code==204
    assert client.get('/api/v1/results/latest').headers['cache-control']=='no-store'
    news=call(client,'/admin/competitions/'+c['id']+'/announcements')
    call(client,'/admin/announcements/'+news[0]['id'],'patch',{'body':'后台修改已保存'})
    again=call(client,'/admin/test-data-imports/preview','post',{})
    assert again['already_imported']
    response=client.post('/api/v1/admin/test-data-imports/'+again['id']+'/commit',json={'content_sha256':again['content_sha256']},headers={'Idempotency-Key':again['id']})
    assert response.json()['data']['id']==batch['id']
    assert call(client,'/announcements/'+news[0]['id'])['body']=='后台修改已保存'


def test_test_results_isolated_draft_freeze_withdraw_and_republish(client):
    imported(client)
    c=next(c for c in call(client,'/admin/competitions') if c['slug']=='autumn')
    base='/admin/competitions/'+c['id']+'/final-results'
    before=call(client,'/competitions/autumn/home')
    public=call(client,'/results/latest')
    draft=call(client,base+'/draft')
    ms=call(client,base+'/test-matches')['items']
    semi=next(m for m in ms if m['champion_path_order']==1)
    semi['wins_b']=0
    call(client,base+'/test-matches','put',{'expected_version':draft['version'],'items':ms})
    assert call(client,'/results/latest')==public
    assert call(client,'/competitions/autumn/home')==before
    publish(client,base)
    assert call(client,'/results/latest')['champion_path'][0]['wins_b']==0
    p=call(client,base+'/draft')
    call(client,base+'/withdraw','post',{'expected_version':p['version'],'reason':'测试撤回'})
    assert call(client,'/results/latest') is None
    call(client,'/competitions/autumn/results',status=404)
    publish(client,base)
    assert call(client,'/results/latest')['champion']['name']=="Poppin'Party"


def test_import_conflict_stale_and_rollback(client):
    pv=call(client,'/admin/test-data-imports/preview','post',{})
    call(client,'/admin/competitions','post',{'slug':'other','name':'其他赛事'})
    r=client.post('/api/v1/admin/test-data-imports/'+pv['id']+'/commit',json={'content_sha256':pv['content_sha256']},headers={'Idempotency-Key':'stale'})
    assert r.status_code==409 and r.json()['error']['code']=='IMPORT_STALE'
    assert len(call(client,'/admin/competitions'))==1
    call(client,'/admin/competitions','post',{'slug':'autumn','name':'既有资料'})
    preview=call(client,'/admin/test-data-imports/preview','post',{})
    assert preview['conflicts']
    r=client.post('/api/v1/admin/test-data-imports/'+preview['id']+'/commit',json={'content_sha256':preview['content_sha256']},headers={'Idempotency-Key':'conflict'})
    assert r.status_code==409
    assert len(call(client,'/admin/competitions'))==2


def test_regular_mode_cannot_bypass_and_cross_edition_rejected(client):
    c,ids,_=setup_competition(client,2,kind=None)
    base='/admin/competitions/'+c['id']+'/final-results'
    call(client,base+'/draft','put',{'expected_version':1,'result_kind':'test'},status=422)
    imported(client)
    autumn=next(c for c in call(client,'/admin/competitions') if c['slug']=='autumn')
    base='/admin/competitions/'+autumn['id']+'/final-results'
    p=call(client,base+'/draft');items=call(client,base+'/test-matches')['items']
    items[0]['a_registration_id']=ids[0]
    call(client,base+'/test-matches','put',{'expected_version':p['version'],'items':items},status=422)
    assert call(client,base+'/draft')['version']==p['version']
    assert call(client,'/results/latest')['champion']['name']=="Poppin'Party"


def test_membership_change_invalidates_test_release_but_live_schedule_does_not(client):
    imported(client)
    c=next(c for c in call(client,'/admin/competitions') if c['slug']=='autumn')
    ms=call(client,'/admin/competitions/'+c['id']+'/matches')
    upcoming=next(m for m in ms if m['a'] and not m['confirmed'])
    call(client,'/admin/matches/'+upcoming['id'],'patch',{'status':'postponed'})
    assert call(client,'/results/latest') is not None
    call(client,'/admin/competitions/'+c['id'],'patch',{'team_limit':5})
    call(client,'/admin/competitions/'+c['id']+'/registrations','post',{'code':'NEW','name':'新增队伍','contact':'内部测试','members':[{'nickname':'新增'+str(i),'steam_id':str(76561199000000400+i),'role':'正式','captain':i==0} for i in range(5)]},status=422)
    from app.main import app
    for db in app.dependency_overrides[db_session]():
        team=db.scalar(select(Registration).where(Registration.competition_id==c['id']))
        team.active=False
        db.flush()
    assert call(client,'/results/latest') is None


def test_committed_dataset_survives_database_engine_restart(tmp_path):
    from sqlalchemy import create_engine, func
    from sqlalchemy.orm import sessionmaker
    from app.db import Base
    from app.test_data import package, import_package
    from app.final_results import visible
    path=tmp_path/'persisted.db'
    engine=create_engine('sqlite:///'+path.as_posix())
    Base.metadata.create_all(engine)
    data,sha=package('public-test','1')
    with sessionmaker(engine).begin() as db:
        import_package(db,data,sha,'persistence')
    engine.dispose()
    restarted=create_engine('sqlite:///'+path.as_posix())
    with sessionmaker(restarted)() as db:
        assert db.scalar(select(func.count()).select_from(Registration))==4
        assert visible(db)[0].public_snapshot['champion']['name']=="Poppin'Party"
        assert db.scalar(select(Competition).where(Competition.slug=='autumn')).status=='ongoing'
    restarted.dispose()
