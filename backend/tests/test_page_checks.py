from .test_platform import client, setup_competition, call

def check(client, path):
    return client.get('/internal/page-check', headers={'X-Original-URI': path}).status_code

def test_page_visibility_and_ownership(client):
    c, ids, stage = setup_competition(client)
    assert check(client, '/competitions/test-cup/schedule?date=2026-11-14') == 204
    assert check(client, '/competitions/test-cup/teams/' + ids[0]) == 204
    other = call(client, '/admin/competitions', 'post', {'name':'Other', 'slug':'other', 'rules':'rules', 'map_pool':['Mirage']})
    call(client, f'/admin/competitions/{other["id"]}/publish', 'post', {})
    assert check(client, '/competitions/other/teams/' + ids[0]) == 403
    from datetime import datetime, timezone, timedelta
    future=call(client,'/admin/announcements','post',{'competition_id':c['id'],'title':'future','body':'future','published':True,'publish_at':(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()})
    assert check(client,'/announcements/'+future['id']) == 403
    matches = call(client, '/competitions/test-cup/matches')
    assert check(client, '/matches/' + matches[0]['id']) == 204
    for path in ['/unknown', '/matches/unknown', '/competitions/missing', '/competitions/test-cup/teams/-1', '/competitions/test-cup/schedule/extra', '/competitions/../other']:
        assert check(client, path) == 403
    from app.db import db_session, Competition
    from app.main import app
    for db in app.dependency_overrides[db_session]():
        db.get(Competition,c['id']).published=False
        db.flush()
    assert check(client, '/competitions/test-cup') == 403
    assert check(client, '/matches/' + matches[0]['id']) == 403
