import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select
from starlette.requests import Request

from app.db import ResultPage, db_session
from app.main import app, login_source
from app.infrastructure.rate_limit import login_limiter
from app.tournaments import generate_graph
from .test_platform import call, client, confirm, setup_competition


def test_confirmed_final_survives_retries(client):
    c, _, _ = setup_competition(client)
    path = f'/admin/competitions/{c["id"]}/matches'
    first, second = [m for m in call(client, path) if m['a'] and m['b']]
    saved = confirm(client, first)
    source = '/admin/matches/' + first['id']
    revised = call(client, source + '/result/revise', 'post', {
        'expected_version':saved['version'], 'reason':'更正胜者',
        'result_type':'forfeit', 'winner':first['b'],
    })
    confirm(client, second)
    final = confirm(client, next(m for m in call(client, path) if not m['confirmed']))
    call(client, source + '/result/confirm', 'post', {'expected_version':revised['version']}, 409)
    call(client, source + '/result/confirm', 'post', {'expected_version':revised['version']-1}, 409)
    assert call(client, source) == revised
    assert call(client, '/admin/matches/' + final['id']) == final


def test_draft_save_preserves_server_owned_awards(client):
    c, _, stage = setup_competition(client)
    path = f'/admin/competitions/{c["id"]}/final-results/draft'
    draft = call(client, path, 'put', {'expected_version':1, 'final_stage_id':stage['id']})
    plan = {'1':['prize-one']}
    for db in app.dependency_overrides[db_session]():
        page = db.scalar(select(ResultPage).where(ResultPage.competition_id == c['id']))
        page.config = {**page.config, 'award_plan':plan}
    result = call(client, path, 'put', {
        'expected_version':draft['version'], 'seal_mode':'team_logo', 'award_plan':{},
    })
    assert result['config']['award_plan'] == plan
    assert result['config']['final_stage_id'] == stage['id']


def test_group_final_preserves_qualified_team_version(client):
    c, _, stage = setup_competition(client, 4, 'group_single', {'groups':1, 'qualify':2})
    matches = f'/admin/competitions/{c["id"]}/matches'
    for match in call(client, matches):
        if match['group']:
            confirm(client, match)
    call(client, f'/admin/stages/{stage["id"]}/qualifications/confirm', 'post', {})
    final = confirm(client, next(m for m in call(client, matches) if not m['group']))
    public = '/matches/' + final['id']
    before = call(client, public)['teams']
    team = next(t for t in call(client, f'/admin/competitions/{c["id"]}/registrations') if t['id'] == final['a'])
    call(client, f'/admin/registrations/{team["id"]}/roster-revisions', 'post', {
        **team, 'name':'新版队名', 'expected_version':team['version'], 'reason':'赛后更新',
    })
    call(client, f'/admin/schedule-generations/{stage["id"]}/publish', 'post', {})
    assert call(client, public)['teams'] == before


def test_manual_groups_must_supply_every_qualifier():
    teams = list('abcdefgh')
    with pytest.raises(HTTPException) as error:
        generate_graph(teams, 'group_single', {
            'groups':2, 'qualify':2, 'manual_groups':[teams[:1], teams[1:]],
        })
    assert error.value.detail['code'] == 'GROUPS'


def test_login_sources_and_success_budget(client, monkeypatch):
    monkeypatch.setenv('LOGIN_TRUSTED_PROXIES', '192.0.2.1,192.0.2.2')
    def source(peer, chain):
        req = Request({'type':'http', 'client':(peer, 1234),
                       'headers':[(b'x-forwarded-for', chain.encode())]})
        return login_source(req)
    visitor = source('192.0.2.1', '198.51.100.4, 192.0.2.2')
    assert visitor == '198.51.100.4'
    assert source('198.51.100.5', visitor) == '198.51.100.5'
    limiter = app.dependency_overrides[login_limiter]()
    for _ in range(10):
        limiter.reserve(visitor)
    with pytest.raises(HTTPException) as limit:
        limiter.reserve(visitor)
    assert limit.value.status_code == 429
    limiter.reserve(source('192.0.2.1', '198.51.100.5, 192.0.2.2'))
    assert 'testclient' not in limiter.attempts


def test_login_transaction_closes_before_sending_cookie(client, monkeypatch):
    dependency = app.dependency_overrides[db_session]
    completed = False

    def observed_transaction():
        nonlocal completed
        yield from dependency()
        completed = True

    async def observe_response(scope, receive, send):
        async def observed_send(message):
            if message['type'] == 'http.response.start':
                assert completed, 'Cannot send a session cookie before the session is persisted'
            await send(message)
        await app(scope, receive, observed_send)

    monkeypatch.setitem(app.dependency_overrides, db_session, observed_transaction)
    with TestClient(observe_response) as browser:
        response = browser.post('/api/v1/admin/auth/login', headers={'origin':'http://localhost:5173'}, json={
            'username':'test-admin', 'password':'testing-only-12!',
        })
        assert response.status_code == 200
        assert 'session' in browser.cookies


def test_clear_live_match_and_preserve_status(client):
    c, _, _ = setup_competition(client, 2)
    match = call(client, f'/admin/competitions/{c["id"]}/matches')[0]
    live = call(client, '/admin/live-streams', 'post', {
        'competition_id':c['id'], 'match_id':match['id'], 'status':'live',
    })
    path = '/admin/live-streams/' + live['id']
    assert call(client, path, 'patch', {})['match_id'] == match['id']
    assert call(client, path, 'patch', {'match_id':''})['match_id'] is None
    assert call(client, path, 'patch', {'match_id':None})['status'] == 'live'


def test_upload_authorization_precedes_body_parser(client, monkeypatch):
    def unexpected_parse(*args, **kwargs):
        pytest.fail('multipart body parsed before authorization')
    monkeypatch.setattr(Request, 'form', unexpected_parse)
    for path in ('/api/v1/admin/assets', '/api/v1/admin/competitions/demo/imports/preview'):
        assert client.post(path, files={'file':('tiny', b'ok')}, headers={'x-csrf-token':'invalid'}).status_code == 403
    client.cookies.clear()
    for path in ('/api/v1/admin/assets', '/api/v1/admin/competitions/demo/imports/preview'):
        assert client.post(path, files={'file':('tiny', b'ok')}).status_code == 401
