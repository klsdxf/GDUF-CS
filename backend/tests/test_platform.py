import io
import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from openpyxl import Workbook
from app.db import Base, Admin, Competition, Registration, Match, Stage, Advancement, db_session
from app.main import app, ph, login_attempts, public_cache, public_locks
from app.tournaments import generate_graph

@pytest.fixture
def client():
    test_url=os.getenv('TEST_DATABASE_URL')
    if test_url:
        assert test_url.rsplit('/',1)[-1]=='gduf_test','仅允许独立 gduf_test 数据库'
        engine=create_engine(test_url)
        Base.metadata.drop_all(engine)
    else:engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine);factory=sessionmaker(engine,expire_on_commit=False)
    def dependency():
        with factory.begin() as db:yield db
    app.dependency_overrides[db_session]=dependency
    with factory.begin() as db:db.add(Admin(id=1,username='test-admin',password_hash=ph.hash('testing-only-12!')))
    login_attempts.clear()
    public_cache.clear();public_locks.clear()
    with TestClient(app) as client:
        client.headers['origin']='http://localhost:5173'
        response=client.post('/api/v1/admin/auth/login',json={'username':'test-admin','password':'testing-only-12!'})
        assert response.status_code==200,response.text
        client.headers['x-csrf-token']=response.json()['data']['csrf']
        yield client
    app.dependency_overrides.clear();engine.dispose()

def call(client,path,method='get',payload=None,status=200):
    r=getattr(client,method)('/api/v1'+path,**({'json':payload} if payload is not None else {}))
    assert r.status_code==status,r.text
    return r.json().get('data')

def setup_competition(client,count=4,kind='single',config=None):
    c=call(client,'/admin/competitions','post',{'name':'测试杯','slug':'test-cup','rules':'测试赛规','map_pool':['Mirage','Inferno','Nuke','Anubis','Ancient']})
    ids=[]
    for t in range(count):
        team={'code':f'T{t:03}','name':f'战队{t}','contact':'private-contact','members':[{'nickname':f'选手{t}-{i}','steam_id':str(76561198000000000+t*10+i),'role':'正式','captain':i==0} for i in range(5)]}
        ids+=call(client,f'/admin/competitions/{c["id"]}/registrations','post',team)
    call(client,f'/admin/competitions/{c["id"]}/publish','post',{})
    if not kind:return c,ids,None
    s=call(client,'/admin/stages','post',{'competition_id':c['id'],'name':'比赛阶段','type':kind,'config':config or {'best_of':1}})
    call(client,f'/admin/stages/{s["id"]}/entries','put',{'entries':ids})
    call(client,f'/admin/stages/{s["id"]}/generate','post',{'idempotency_key':'generation-1'})
    call(client,f'/admin/schedule-generations/{s["id"]}/publish','post',{})
    return c,ids,s

def confirm(client,m,winner='a'):
    r=call(client,f'/admin/matches/{m["id"]}/result','put',{'expected_version':m['version'],'maps':[{'map_name':'Mirage','score_a':13 if winner=='a' else 6,'score_b':6 if winner=='a' else 13}]})
    return call(client,f'/admin/matches/{m["id"]}/result/confirm','post',{'expected_version':r['version']})

@pytest.mark.parametrize('n',[2,3,5,16,20,24,28,32])
def test_single_graph(n):
    nodes,edges=generate_graph([str(i) for i in range(n)],'single',{'best_of':3})
    assert len(nodes)==n-1
    assert len({(e['target'],e['slot']) for e in edges})==len(edges)
    assert all(m['a']!=m['b'] or m['a'] is None for m in nodes)

@pytest.mark.parametrize('n',[2,3,4,5,16,32])
@pytest.mark.parametrize('reset',[False,True])
def test_double_paths(n,reset):
    nodes,edges=generate_graph([str(i) for i in range(n)],'double',{'grand_final_reset':reset})
    resolved={};losses={str(i):0 for i in range(n)}
    for node in nodes:
        slots={k:node[k] for k in ('a','b')}
        for edge in edges:
            if edge['target']==node['code']:slots[edge['slot']]=resolved[(edge['source'],edge['outcome'])]
        assert slots['a'] is not None and slots['b'] is not None
        assert slots['a']!=slots['b']
        if node['bracket']=='reset':continue
        assert losses[slots['a']]<2 and losses[slots['b']]<2
        winner=slots['b'] if node['bracket']=='final' and reset else slots['a']
        loser=slots['b'] if winner==slots['a'] else slots['a'];losses[loser]+=1
        resolved[(node['code'],'winner')]=winner;resolved[(node['code'],'loser')]=loser
    assert len(nodes)==2*n-2+int(reset)

@pytest.mark.parametrize('n,groups',[(20,5),(24,6),(28,7)])
def test_group_non_power_two(n,groups):
    nodes,edges=generate_graph([str(i) for i in range(n)],'group_single',{'groups':groups,'qualify':2})
    assert sum(m['group']!='' for m in nodes)==groups*6
    assert sum(m['bracket']=='playoff' for m in nodes)==groups*2-1

def test_auth_privacy_and_hidden_content(client):
    c,ids,s=setup_competition(client)
    for path in ('/teams','/matches','/home'):
        r=client.get('/api/v1/competitions/'+c['id']+path)
        assert r.status_code==200
        assert 'private-contact' not in r.text and 'steam_id' not in r.text and '7656119' not in r.text
    r=client.post('/api/v1/admin/competitions',json={'name':'bad'})
    assert r.status_code==422
    client.headers['x-csrf-token']='wrong'
    assert client.post('/api/v1/admin/competitions',json={}).status_code==403
    client.cookies.clear()
    assert client.post('/api/v1/admin/competitions',json={}).status_code==401

def test_complete_single_event_and_revisions(client):
    c,ids,s=setup_competition(client)
    matches=call(client,f'/admin/competitions/{c["id"]}/matches')
    first=next(m for m in matches if m['a'] and m['b'])
    saved=confirm(client,first)
    call(client,f'/admin/matches/{first["id"]}/result/confirm','post',{'expected_version':saved['version']-1})
    revised=call(client,f'/admin/matches/{first["id"]}/result/revise','post',{'expected_version':saved['version'],'reason':'录入纠正','maps':[{'map_name':'Mirage','score_a':6,'score_b':13}]})
    assert revised['winner']==first['b']
    matches=call(client,f'/admin/competitions/{c["id"]}/matches')
    second=next(m for m in matches if m['a'] and m['b'] and not m['confirmed']);confirm(client,second)
    matches=call(client,f'/admin/competitions/{c["id"]}/matches')
    final=next(m for m in matches if not m['confirmed'])
    call(client,f'/admin/matches/{final["id"]}','patch',{'status':'ongoing'})
    call(client,f'/admin/matches/{first["id"]}/result/revise','post',{'expected_version':revised['version'],'reason':'不允许覆盖下游','maps':[{'map_name':'Mirage','score_a':13,'score_b':6}]},409)
    confirm(client,final)
    call(client,f'/admin/competitions/{c["id"]}/archive','post',{})
    assert call(client,'/competitions/test-cup')['status']=='archived'

def workbook(count=16,bad=False):
    wb=Workbook();t=wb.active;t.title='队伍';t.append(['队伍编号','队伍名称','队伍简介','队长联系方式'])
    m=wb.create_sheet('成员');m.append(['队伍编号','游戏昵称','Steam ID','成员类型','是否队长'])
    for i in range(count):
        code=f'T{i:03}';t.append([code,f'战队{i}','','private-contact'])
        for j in range(5):m.append([code,f'队员{j}',76561198000000000 if bad and i==0 else str(76561198000000000+i*10+j),'正式','是' if j==0 else '否'])
    out=io.BytesIO();wb.save(out);return out.getvalue()

def preview(client,c,raw,mode='create'):
    r=client.post('/api/v1/admin/competitions/'+c['id']+'/imports/preview',files={'file':('roster.xlsx',raw)},data={'mode':mode})
    assert r.status_code==200,r.text
    return r.json()['data']

def test_excel_atomicity_stale_and_retry(client):
    c=call(client,'/admin/competitions','post',{'name':'导入测试','slug':'import'})
    bad=preview(client,c,workbook(bad=True));assert bad['payload']['errors']
    call(client,f'/admin/imports/{bad["id"]}/commit','post',{'idempotency_key':'x'},422)
    assert call(client,f'/admin/competitions/{c["id"]}/registrations')==[]
    a=preview(client,c,workbook());b=preview(client,c,workbook())
    assert not a['payload']['errors'],a
    call(client,f'/admin/imports/{a["id"]}/commit','post',{'idempotency_key':'x'})
    call(client,f'/admin/imports/{a["id"]}/commit','post',{'idempotency_key':'x'})
    assert len(call(client,f'/admin/competitions/{c["id"]}/registrations'))==16
    call(client,f'/admin/imports/{b["id"]}/commit','post',{'idempotency_key':'y'},409)
    duplicate=preview(client,c,workbook());assert duplicate['payload']['errors']
    update=preview(client,c,workbook(),'update');assert not update['payload']['errors']
    call(client,f'/admin/imports/{update["id"]}/commit','post',{'idempotency_key':'z'})

def test_announcement_visibility_and_password_logout(client):
    c,_,_=setup_competition(client,2,kind=None)
    a=call(client,'/admin/announcements','post',{'competition_id':c['id'],'title':'未来公告','body':'正文','published':True,'publish_at':'2099-01-01T00:00:00+08:00'})
    call(client,'/announcements/'+a['id'],status=404)
    assert call(client,f'/competitions/{c["id"]}/announcements')==[]
    call(client,'/admin/auth/password','put',{'current_password':'testing-only-12!','password':'new-testing-only-12!'})
    call(client,'/admin/auth/me',status=401)

@pytest.mark.parametrize('bo',[1,3,5])
def test_bo_completion_and_reject_extra_maps(client,bo):
    c,ids,s=setup_competition(client,2,config={'best_of':bo})
    m=call(client,f'/admin/competitions/{c["id"]}/matches')[0]
    needed=bo//2+1
    maps=[{'map_name':name,'score_a':13,'score_b':7} for name in c['map_pool'][:needed]]
    if needed>1:
        r=call(client,f'/admin/matches/{m["id"]}/result','put',{'expected_version':0,'maps':maps[:-1]})
        call(client,f'/admin/matches/{m["id"]}/result/confirm','post',{'expected_version':r['version']},422)
        m=r
    r=call(client,f'/admin/matches/{m["id"]}/result','put',{'expected_version':m['version'],'maps':maps})
    r=call(client,f'/admin/matches/{m["id"]}/result/confirm','post',{'expected_version':r['version']})
    assert r['result']['wins_a']==needed
    call(client,f'/admin/matches/{m["id"]}/result/revise','post',{'expected_version':r['version'],'reason':'超额地图','maps':maps+[{'map_name':c['map_pool'][needed],'score_a':13,'score_b':6}]},422)

def test_roster_revision_keeps_match_identity_and_members(client):
    c,ids,s=setup_competition(client)
    teams=call(client,f'/admin/competitions/{c["id"]}/registrations')
    team=teams[0]
    m=next(m for m in call(client,f'/admin/competitions/{c["id"]}/matches') if team['id'] in (m['a'],m['b']))
    before=call(client,'/matches/'+m['id'])
    team['name']='修订后的队名';team['members'][0]['nickname']='修订昵称'
    call(client,'/admin/registrations/'+team['id'],'patch',team,422)
    call(client,'/admin/registrations/'+team['id']+'/roster-revisions','post',{**team,'expected_version':team['version'],'reason':'组织方批准变更'})
    after=call(client,'/matches/'+m['id'])
    assert before['teams']==after['teams']
    assert call(client,f'/competitions/{c["id"]}/teams/{team["id"]}')['name']=='修订后的队名'

def test_group_qualification_and_result_revision_blockers(client):
    c,ids,s=setup_competition(client,4,'group_single',{'best_of':1,'groups':1,'qualify':2})
    group= [m for m in call(client,f'/admin/competitions/{c["id"]}/matches') if m['group']]
    results=[confirm(client,m) for m in group]
    call(client,f'/admin/stages/{s["id"]}/qualifications/confirm','post',{})
    final=next(m for m in call(client,f'/admin/competitions/{c["id"]}/matches') if not m['group'])
    assert final['a'] and final['b']
    call(client,f'/admin/matches/{final["id"]}','patch',{'status':'ongoing'})
    m=results[0];payload={'expected_version':m['version'],'reason':'修正','maps':[{'map_name':'Mirage','score_a':6,'score_b':13}]}
    call(client,f'/admin/matches/{m["id"]}/result/revise','post',payload,409)
    call(client,f'/admin/matches/{final["id"]}','patch',{'status':'scheduled'})
    call(client,f'/admin/matches/{m["id"]}/result/revise','post',payload)
    final=next(m for m in call(client,f'/admin/competitions/{c["id"]}/matches') if not m['group'])
    assert not final['a'] and not final['b']

def test_hidden_draft_and_login_origin(client):
    c=call(client,'/admin/competitions','post',{'slug':'hidden','name':'草稿'})
    call(client,'/competitions/'+c['id'],status=404)
    call(client,'/admin/auth/logout','post',{})
    client.headers['origin']='https://untrusted.example'
    call(client,'/admin/auth/login','post',{'username':'test-admin','password':'testing-only-12!'},403)

def test_repeated_generation_and_publication(client):
    c,ids,s=setup_competition(client)
    call(client,f'/admin/stages/{s["id"]}/generate','post',{'idempotency_key':'different'},409)
    call(client,f'/admin/schedule-generations/{s["id"]}/publish','post',{})
    assert len(call(client,f'/admin/competitions/{c["id"]}/matches'))==3
