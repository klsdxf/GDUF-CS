"""Two independent processes with real PostgreSQL and Redis. Run only in the isolated integration job."""
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import socket
import subprocess
import sys
import time
from threading import Barrier
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import event, select
from sqlalchemy.engine import make_url

from app.db import Admin, Audit, CacheInvalidation, OperationReceipt, ResultRelease, Session, engine
from app.infrastructure.cache import FILL, READ
from app.infrastructure.redis_client import CONTROL, client as get_redis, key
from app.jobs.cache_outbox import maintain
from app.main import ph
from .test_platform import call, preview, setup_competition, workbook
from .test_final_results import add_awards, prepare

pytestmark = pytest.mark.skipif(not os.getenv('QUALITY_REDIS_URL'), reason='requires isolated real services')
ORIGIN = 'http://127.0.0.1:5173'
PASSWORD = 'integration-only-12!'


def port():
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        return listener.getsockname()[1]


def until(check, seconds=20):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            if check():
                return
        except (httpx.TransportError, OSError):
            pass
        time.sleep(0.1)
    pytest.fail('condition timed out')


@pytest.fixture(scope='module')
def installation(tmp_path_factory):
    url = make_url(os.environ['DATABASE_URL'])
    assert os.getenv('GDUF_TEST_ISOLATED') == '1'
    assert url.host in ('localhost', '127.0.0.1') and url.database == 'gduf_quality'
    workdir = Path(__file__).parents[1]
    directory = tmp_path_factory.mktemp('dual-api')
    namespace = f'gduf:ci:{uuid4().hex}'
    with pytest.MonkeyPatch.context() as env:
        env.setenv('REDIS_URL', os.environ['QUALITY_REDIS_URL'])
        env.setenv('REDIS_NAMESPACE', namespace)
        env.setenv('LOGIN_SOURCE_SECRET', 'ci-test-only-shared-secret')
        env.setenv('LOGIN_TRUSTED_PROXIES', '127.0.0.1')
        env.setenv('PUBLIC_ORIGIN', ORIGIN)
        env.setenv('MEDIA_DIR', str(directory/'media'))
        get_redis.cache_clear()
        subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'], cwd=workdir, check=True, timeout=45)
        with Session.begin() as db:
            admin = db.get(Admin, 1)
            if not admin:
                db.add(Admin(id=1, username='integration', password_hash=ph.hash(PASSWORD)))
        redis = get_redis()
        maintain(redis)
        # Check the initial protection, then release it explicitly in this disposable namespace.
        until(lambda: redis.hget(key(CONTROL), 'ready') == b'1')
        assert int(redis.hget(key(CONTROL), 'login_until')) > int(time.time() * 1000) + 280_000
        redis.hset(key(CONTROL), 'login_until', 0)
        processes = []
        clients = []
        try:
            for i in range(2):
                api_port = port()
                with (directory/f'api-{i}.log').open('w', encoding='utf-8') as log:
                    processes.append(subprocess.Popen(
                        [sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1',
                         '--port', str(api_port), '--no-proxy-headers', '--no-access-log'],
                        cwd=workdir, stdout=log, stderr=subprocess.STDOUT))
                client = httpx.Client(base_url=f'http://127.0.0.1:{api_port}', timeout=8,
                                      headers={'Origin': ORIGIN, 'X-Forwarded-For': f'192.0.2.{12+i}'})
                clients.append(client)
                until(lambda: client.get('/health/ready').status_code == 200)
            yield (*clients, redis)
        finally:
            for process in processes:
                process.terminate()
                try:
                    process.wait(10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(5)
            for client in clients:
                client.close()
            redis.close()
            get_redis.cache_clear()


def login(client, password, source):
    return client.post('/api/v1/admin/auth/login', headers={'X-Forwarded-For': source},
                       json={'username': 'integration', 'password': password})


def log_in(client, source):
    response = login(client, PASSWORD, source)
    assert response.status_code == 200, response.text
    client.headers['x-csrf-token'] = response.json()['data']['csrf']


def test_shared_login_cache_cas_and_query_budget(installation, monkeypatch):
    a, b, redis = installation
    source = '198.51.100.10'
    for i in range(9):
        assert login((a, b)[i % 2], 'bad', source).status_code == 401
    log_in(b, source)
    assert login(a, 'bad', source).status_code == 401
    rejected = login(b, PASSWORD, source)
    assert rejected.status_code == 429 and int(rejected.headers['Retry-After']) > 0
    log_in(a, '198.51.100.11')
    assert login(a, 'bad', '198.51.100.12').status_code == 401
    assert all(0 < redis.pttl(k) <= 300000 for k in redis.scan_iter(key('limit:*')))

    c, _, _ = setup_competition(a, count=32, slug=f'quality-{uuid4().hex}')
    path = f'/api/v1/competitions/{c["id"]}/matches'
    cold = a.get(path)
    assert cold.status_code == 200, cold.text
    hot = b.get(path)
    assert hot.json() == cold.json()
    assert hot.headers['x-request-id'] != cold.headers['x-request-id']
    assert 'event="cache_hit"' in b.get('/internal/metrics').text

    from app.public import matches
    monkeypatch.setenv('PUBLIC_CACHE_DISABLED', '1')
    statements = []
    def capture(connection, cursor, statement, parameters, context, many):
        if statement.lstrip().upper().startswith('SELECT'):
            statements.append(statement)
    event.listen(engine, 'before_cursor_execute', capture)
    try:
        assert len(matches(c['id'])['data']) == 31
        assert len(statements) <= 10
    finally:
        event.remove(engine, 'before_cursor_execute', capture)

    match = next(m for m in call(a, f'/admin/competitions/{c["id"]}/matches') if m['a'] and m['b'])
    action = f'/api/v1/admin/matches/{match["id"]}/result'
    payload = {'expected_version': match['version'], 'maps': [{'map_name': 'Mirage', 'score_a': 13, 'score_b': 7}]}
    barrier = Barrier(2)
    def save(client):
        barrier.wait(5)
        return client.put(action, json=payload)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(save, (a, b)))
    assert sorted(r.status_code for r in responses) == [200, 409]
    saved = next(r.json()['data'] for r in responses if r.status_code == 200)
    version = {'expected_version': saved['version']}
    headers = {'Idempotency-Key': 'confirm-once'}
    first = a.post(action+'/confirm', json=version, headers=headers)
    assert first.status_code == 200, first.text
    second = b.post(action+'/confirm', json=version, headers=headers)
    assert first.json() == second.json()
    assert a.post(action+'/confirm', json={'expected_version': saved['version']+1}, headers=headers).status_code == 409
    assert any(m['id'] == match['id'] and m['confirmed'] for m in b.get(path).json()['data'])
    with Session() as db:
        confirmations = db.scalars(select(Audit).where(Audit.entity_id == match['id'], Audit.action == 'result.confirm')).all()
        assert len(confirmations) == 1


def test_old_refill_and_outbox_replay(installation):
    a, b, redis = installation
    control = key(CONTROL)
    data_key, lease_key = key('test-old-value'), key('test-old-lease')
    generation = redis.eval(READ, 2, control, data_key, 'digest')
    redis.set(lease_key, 'previous-owner', px=2000)
    with Session.begin() as db:
        db.add(CacheInvalidation(id='quality-replay-'+uuid4().hex))
    maintain(redis)
    accepted = redis.eval(FILL, 3, control, data_key, lease_key, generation[1], 'previous-owner',
                          generation[2] + 2000, 'old-data')
    assert accepted == 0 and redis.get(data_key) is None
    with Session() as db:
        assert not db.scalar(select(CacheInvalidation.id).where(CacheInvalidation.completed_at.is_(None)))


def test_result_rollback_does_not_publish_or_enqueue(installation, monkeypatch):
    from app.services import result_service

    a, _, redis = installation
    log_in(a, '198.51.100.20')
    c, _, _ = setup_competition(a, slug=f'quality-rollback-{uuid4().hex}')
    path = f'/admin/competitions/{c["id"]}/matches'
    match = next(m for m in call(a, path) if m['a'] and m['b'])
    payload = {'expected_version': match['version'], 'maps': [{'map_name': 'Mirage', 'score_a': 13, 'score_b': 7}]}
    saved = call(a, f'/admin/matches/{match["id"]}/result', 'put', payload)
    before = call(a, path)
    with Session() as db:
        event_ids = set(db.scalars(select(CacheInvalidation.id)))
    original_audit = result_service.audit

    def reject_after_flush(db, action, identifier, data):
        original_audit(db, action, identifier, data)
        db.flush()
        raise RuntimeError('fixture: fail after applying result and auditing')

    monkeypatch.setattr(result_service, 'audit', reject_after_flush)
    with pytest.raises(RuntimeError, match='fixture'):
        with Session.begin() as db:
            result_service.confirm_result(db, match['id'], {'expected_version': saved['version']}, 'rolled-back')
    maintain(redis)
    assert call(a, path) == before
    with Session() as db:
        assert set(db.scalars(select(CacheInvalidation.id))) == event_ids
        assert not db.scalar(select(Audit.id).where(Audit.entity_id == match['id'], Audit.action == 'result.confirm'))
        assert not db.scalar(select(OperationReceipt.action).where(OperationReceipt.resource_id == match['id'],
                                                                  OperationReceipt.action == 'result.confirm'))


def test_result_release_race_and_import_retry(installation):
    a, b, _ = installation
    log_in(a, '198.51.100.21')
    log_in(b, '198.51.100.22')
    c, _, _, base, page = prepare(a, count=2, slug=f'quality-race-{uuid4().hex}')
    page = add_awards(a, c, base, page)
    check = call(a, base+'/validate', 'post', {'expected_version': page['version']})
    assert not check['blocking_errors']
    match = call(a, '/admin/matches/'+page['config']['final_match_id'])
    barrier = Barrier(2)

    def publish():
        barrier.wait(5)
        return a.post('/api/v1'+base+'/publish', headers={'Idempotency-Key':'publish-race'}, json={
            'expected_version': page['version'], 'expected_source_fingerprint': check['source_fingerprint'],
            'reason': 'integration race',
        })

    def revise():
        barrier.wait(5)
        return b.post('/api/v1/admin/matches/'+match['id']+'/result/revise', json={
            'expected_version': match['version'], 'reason': 'integration correction',
            'maps': [{'map_name': 'Mirage', 'score_a': 13, 'score_b': 10}],
        })

    with ThreadPoolExecutor(max_workers=2) as pool:
        publication, revision = [future.result(10) for future in (pool.submit(publish), pool.submit(revise))]
    assert revision.status_code == 200, revision.text
    assert publication.status_code in (200, 409), publication.text
    assert b.get(f'/api/v1/competitions/{c["id"]}/results').status_code == 404
    if publication.status_code == 200:
        with Session() as db:
            release = db.get(ResultRelease, publication.json()['data']['id'])
            assert release.status == 'invalidated'

    c = call(a, '/admin/competitions', 'post', {'name': 'Import race', 'slug': f'quality-import-{uuid4().hex}'})
    batch = preview(a, c, workbook())
    barrier = Barrier(2)
    def submit(client):
        barrier.wait(5)
        return client.post(f'/api/v1/admin/imports/{batch["id"]}/commit', json={'idempotency_key': 'import-once'})
    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = pool.map(submit, (a, b))
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    with Session() as db:
        assert len(list(db.scalars(select(Audit.id).where(
            Audit.entity_id == batch['id'], Audit.action == 'import.commit')))) == 1


def test_redis_refuses_writes_and_restarts_without_exposing_old_state(installation):
    a, b, redis = installation
    log_in(a, '198.51.100.18')
    maximum = redis.config_get('maxmemory')['maxmemory']
    policy = redis.config_get('maxmemory-policy')['maxmemory-policy']
    redis.config_set('maxmemory-policy', 'noeviction')
    redis.config_set('maxmemory', 1)
    try:
        assert login(b, PASSWORD, '198.51.100.19').status_code == 503
        assert b.get('/api/v1/competitions').status_code == 200
        assert a.get('/api/v1/admin/auth/me').status_code == 200
    finally:
        redis.config_set('maxmemory', maximum)
        redis.config_set('maxmemory-policy', policy)

    container = os.getenv('QUALITY_REDIS_CONTAINER')
    if not container:
        pytest.skip('Redis restart fixture not provided')
    assert container.isalnum() or container.startswith('gduf-quality-')
    subprocess.run(['docker', 'stop', '-t', '0', container], check=True, timeout=25)
    try:
        assert login(b, PASSWORD, '198.51.100.19').status_code == 503
        assert b.get('/api/v1/competitions').status_code == 200
        assert a.get('/api/v1/admin/auth/me').status_code == 200
        a.post('/api/v1/admin/competitions', json={
            'name': 'Outbox during outage', 'slug': f'quality-outage-{uuid4().hex}',
        }).raise_for_status()
        with Session() as db:
            assert db.scalar(select(CacheInvalidation.id).where(CacheInvalidation.completed_at.is_(None)))
    finally:
        subprocess.run(['docker', 'start', container], check=True, timeout=25)
    from redis.exceptions import RedisError
    def recovered():
        try:
            maintain(redis)
            return redis.hget(key(CONTROL), 'ready') == b'1'
        except RedisError:
            return False
    until(recovered)
    assert login(b, PASSWORD, '198.51.100.19').status_code == 503
    assert b.get('/internal/components').json()['data']['redis'] == 'login_protected'
    with Session() as db:
        assert not db.scalar(select(CacheInvalidation.id).where(CacheInvalidation.completed_at.is_(None)))
