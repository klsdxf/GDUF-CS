from .test_platform import client, call, setup_competition, confirm
from app.db import ResultRelease

def prepare(client,kind='single',count=4,config=None,reset_trigger=False):
    c,ids,s=setup_competition(client,count,kind,config)
    for _ in range(30):
        ms=call(client,f'/admin/competitions/{c["id"]}/matches')
        ready=[m for m in ms if m['a'] and m['b'] and not m['confirmed'] and m['status']!='cancelled']
        if not ready:break
        for m in ready:confirm(client,m,'b' if reset_trigger and m['bracket']=='final' else 'a')
    call(client,f'/admin/competitions/{c["id"]}','patch',{'status':'completed'})
    b=f'/admin/competitions/{c["id"]}/final-results'
    p=call(client,b+'/draft','put',{'expected_version':1,'final_stage_id':s['id'],'display_meta':{'edition_label':'测试杯','seal_edition_label':'TEST','seal_serial':'007'}})
    p=call(client,b+'/calculate','post',{'expected_version':p['version']})
    return c,ids,s,b,p

def add_awards(client,c,b,p,tier='presenting'):
    sponsor=call(client,'/admin/sponsors','post',{'name':'实际品牌','english_name':'REAL','introduction':'支持赛事'})
    partner=call(client,f'/admin/competitions/{c["id"]}/partners','post',{'expected_version':p['version'],'sponsor_id':sponsor['id'],'tier':tier,'published':True})
    p=call(client,b+'/draft')
    prize=call(client,f'/admin/competitions/{c["id"]}/prizes','post',{'expected_version':p['version'],'provider_partner_id':partner['id'],'name':'正式奖品','unit':'件','category':'equipment','builtin_illustration_key':'mouse'})
    p=call(client,b+'/draft')
    call(client,b+'/allocations','put',{'expected_version':p['version'],'items':[{'placement_id':r['id'],'prize_id':prize['id'],'quantity':r['recipient_count'],'distribution':'per_recipient','per_recipient_quantity':1} for r in p['placements']]})
    return call(client,b+'/draft')

def test_publish_snapshot_withdraw_and_invalidation(client):
    c,ids,s,b,p=prepare(client)
    assert [(r['rank_from'],r['rank_to']) for r in p['placements']]==[(1,1),(2,2),(3,4),(3,4)]
    assert client.get('/api/v1/results/latest').json()['data'] is None
    p=add_awards(client,c,b,p)
    v=call(client,b+'/validate','post',{'expected_version':p['version']})
    assert v['blocking_errors']==[],v
    payload={'expected_version':p['version'],'expected_source_fingerprint':v['source_fingerprint'],'reason':'正式公布'}
    response=client.post('/api/v1'+b+'/publish',json=payload,headers={'Idempotency-Key':'once'})
    assert response.status_code==200,response.text
    release=response.json()['data']
    again=client.post('/api/v1'+b+'/publish',json=payload,headers={'Idempotency-Key':'once'})
    assert again.json()['data']['id']==release['id']
    public=call(client,'/results/latest')
    assert public['champion']['team_id']==ids[0]
    assert public['support_totals']['equipment']==20
    import json
    assert all(k not in json.dumps(public) for k in ('private-contact','steam_id','draft_result','ruling_reason'))
    assert client.get('/api/v1/results/latest').headers['cache-control']=='no-store'
    call(client,b+'/draft','put',{'expected_version':p['version']},status=409)
    p=call(client,b+'/draft')
    call(client,b+'/draft','put',{**p['config'],'expected_version':p['version'],'display_meta':{'edition_label':'新标题'}})
    assert call(client,'/results/latest')['display'].get('edition_label')=='测试杯'
    final_id=p['config']['final_match_id'];m=call(client,'/admin/matches/'+final_id)
    impact=call(client,f'/admin/matches/{final_id}/result/revise-preview','post',{'maps':[{'map_name':'Mirage','score_a':13,'score_b':7}]})
    assert release['id'] in impact['affected_releases']
    call(client,f'/admin/matches/{final_id}/result/revise','post',{'expected_version':m['version'],'reason':'修正比分','maps':[{'map_name':'Mirage','score_a':13,'score_b':7}]})
    assert call(client,'/results/latest') is None
    call(client,'/competitions/test-cup/results',status=404)
    assert call(client,b+'/releases')[0]['status']=='invalidated'


def test_incomplete_source_changed_and_cross_edition(client):
    c,ids,s,b,p=prepare(client)
    v=call(client,b+'/validate','post',{'expected_version':p['version']})
    assert any(x['code']=='PUBLISH_INCOMPLETE' for x in v['blocking_errors'])
    bad=client.post('/api/v1'+b+'/publish',json={'expected_version':p['version'],'expected_source_fingerprint':'wrong','reason':'x'},headers={'Idempotency-Key':'wrong'})
    assert bad.status_code==409
    call(client,b+'/path','put',{'expected_version':p['version'],'items':[{'match_id':'other-edition'}]},status=422)
    call(client,b+'/placements','put',{'expected_version':p['version'],'items':[{'registration_id':'other-edition','rank_from':1,'rank_to':1,'team_display_version':1,'recipient_count':5}]},status=422)
    call(client,'/admin/sponsors','post',{'name':'x','logo_url':'https://example.com/a.svg'},status=422)
    assert client.get('/api/v1/admin/competitions/'+c['id']+'/final-results/preview',cookies={'session':'invalid'}).status_code==401


def test_same_tier_partners_publish_in_stable_order_and_preserve_snapshot(client):
    c,_,_,b,p=prepare(client)
    p=add_awards(client,c,b,p,tier='official')
    partner_path=f'/admin/competitions/{c["id"]}/partners'
    original=call(client,partner_path)[0]
    for name,published,active in [('第二品牌',True,True),('未公开',False,True),('已停用',True,False)]:
        brand=call(client,'/admin/sponsors','post',{'name':name,'active':active})
        call(client,partner_path,'post',{'sponsor_id':brand['id'],'published':published,'expected_version':p['version']})
        p=call(client,b+'/draft')
    preview=call(client,b+'/preview')
    assert preview['presenting_partner'] is None
    assert {item['name'] for item in preview['partners']}=={'实际品牌','第二品牌'}
    assert [item['id'] for item in preview['partners']]==sorted(item['id'] for item in preview['partners'])
    validation=call(client,b+'/validate','post',{'expected_version':p['version']})
    assert not validation['blocking_errors']
    response=client.post('/api/v1'+b+'/publish',json={
        'expected_version':p['version'],'expected_source_fingerprint':validation['source_fingerprint'],
        'reason':'发布同级赞助商',
    },headers={'Idempotency-Key':'peer-partners'})
    assert response.status_code==200,response.text
    p=call(client,b+'/draft')
    path='/admin/competition-partners/'+original['id']
    call(client,path,'patch',{**original,'expected_version':p['version'],'display_order':1.5},status=422)
    call(client,path,'patch',{**original,'expected_version':p['version'],'published':False,'display_order':10})
    p=call(client,b+'/draft')
    validation=call(client,b+'/validate','post',{'expected_version':p['version']})
    assert any('正式奖品' in error['message'] and '提供方' in error['message'] for error in validation['blocking_errors'])
    assert call(client,'/results/latest')['partners']==preview['partners']
    assert [item['name'] for item in call(client,b+'/preview')['partners']]==['第二品牌']


def test_double_reset_and_full_field(client):
    c,ids,s,b,p=prepare(client,'double',8,{'best_of':1,'grand_final_reset':True})
    assert len(p['placements'])==8
    assert p['placements'][0]['registration_id']==ids[0]
    assert p['placements'][0]['rank_from']==1
    assert len(call(client,b+'/preview')['champion_path'])>=3


def test_allocated_prize_can_publish_with_provider_pending(client):
    c,_,_,b,p=prepare(client)
    p=add_awards(client,c,b,p,tier='official')
    prize=call(client,f'/admin/competitions/{c["id"]}/prizes')[0]
    changed=call(client,'/admin/prizes/'+prize['id'],'patch',{
        **prize,'provider_partner_id':None,'expected_version':p['version'],
    })
    assert changed['provider_partner_id'] is None
    p=call(client,b+'/draft')
    validation=call(client,b+'/validate','post',{'expected_version':p['version']})
    assert not validation['blocking_errors']
    response=client.post('/api/v1'+b+'/publish',json={
        'expected_version':p['version'],'expected_source_fingerprint':validation['source_fingerprint'],
        'reason':'奖品提供方待赞助',
    },headers={'Idempotency-Key':'pending-provider'})
    assert response.status_code==200,response.text
    public=call(client,'/results/latest')
    assert public['prizes'][0]['provider_partner_id'] is None
    assert public['support_totals']['equipment']==20
    assert public['partners'][0]['id']==prize['provider_partner_id']


import pytest
import os
@pytest.mark.parametrize('count',[16,32])
def test_full_rankings_large_fields(client,count):
    c,ids,s,b,p=prepare(client,count=count)
    assert len(p['placements'])==count
    groups={}
    for r in p['placements']:groups.setdefault((r['rank_from'],r['rank_to']),[]).append(r)
    assert all(len(g)==end-start+1 for (start,end),g in groups.items())


def test_triggered_reset_is_decisive(client):
    c,ids,s,b,p=prepare(client,'double',4,{'best_of':1,'grand_final_reset':True},True)
    final=call(client,'/admin/matches/'+p['config']['final_match_id'])
    assert final['bracket']=='reset' and final['confirmed']
    assert p['placements'][0]['registration_id']==final['winner']


@pytest.mark.skipif(not os.getenv('TEST_DATABASE_URL'),reason='requires isolated PostgreSQL service')
def test_postgres_draft_cas(client):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    c,ids,s,b,p=prepare(client)
    barrier=Barrier(2)
    def write(i):
        barrier.wait()
        return client.put('/api/v1'+b+'/draft',json={**p['config'],'expected_version':p['version'],'display_meta':{'edition_label':str(i)}}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        codes=list(pool.map(write,[1,2]))
    assert sorted(codes)==[200,409]
