from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
import os
from threading import Barrier
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app import visits
from app.db import AdminSession, Base, VisitDailyTotal, VisitVisitorDay, db_session, now
from app.main import app
from app.security import digest

COLLECT = '/api/v1/visits'
SUMMARY = '/api/v1/admin/visits/summary'
ORIGIN = 'http://localhost:5173'
MIDNIGHT = datetime(2026, 11, 18, 16, tzinfo=timezone.utc)


@pytest.fixture
def stats(tmp_path, monkeypatch):
    engine = create_engine('sqlite:///' + (tmp_path / 'visits.db').as_posix())
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine)
    clock = [MIDNIGHT - timedelta(seconds=15)]

    def transaction():
        with factory.begin() as db:
            yield db

    monkeypatch.setitem(app.dependency_overrides, db_session, transaction)
    monkeypatch.setattr(visits, 'now', lambda: clock[0])
    monkeypatch.setenv('VISIT_STATS_START_DATE', '2026-11-18')
    monkeypatch.setenv('PUBLIC_ORIGIN', ORIGIN)
    with factory.begin() as db:
        db.add(AdminSession(token_hash=digest('stats-session'), csrf='test', expires_at=now() + timedelta(hours=1)))
    with TestClient(app, headers={'origin': ORIGIN}) as client:
        yield client, factory, clock
    engine.dispose()


def test_visits_permissions_and_validation(stats, monkeypatch):
    client, factory, _ = stats
    payload = {'visitor_id': str(uuid4()), 'kind': 'page_view'}
    assert client.get(SUMMARY).status_code == 401
    assert client.post(COLLECT, json=payload, headers={'origin': 'https://outside.example'}).status_code == 403
    for invalid in ({**payload, 'visitor_id': 'invalid'}, {**payload, 'kind': 'other'}, {**payload, 'url': '/'}):
        response = client.post(COLLECT, json=invalid)
        assert response.status_code == 422 and 'no-store' in response.headers['cache-control']
        assert payload['visitor_id'] not in response.text
    assert client.post(COLLECT, content='invalid').status_code == 415
    assert client.post(COLLECT, content=b'x' * 1025, headers={'content-type': 'application/json'}).status_code == 413

    client.cookies.set('session', 'stats-session')
    monkeypatch.setenv('VISIT_STATS_START_DATE', '')
    assert client.post(COLLECT, json=payload).json() == {'data': None}
    assert client.get(SUMMARY).json()['data']['online'] is None
    assert client.get(SUMMARY + '?days=8').status_code == 422
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(VisitVisitorDay)) == 0


def test_visits_online_and_daily_totals_across_midnight(stats):
    client, factory, clock = stats
    client.cookies.set('session', 'stats-session')
    first, second = str(uuid4()), str(uuid4())

    def submit(visitor, kind='page_view'):
        response = client.post(COLLECT, json={'visitor_id': visitor, 'kind': kind})
        assert response.status_code == 200, response.text

    submit(first)
    submit(first)
    submit(second)
    snapshot = client.get(SUMMARY).json()['data']
    assert snapshot['online'] == 2
    assert snapshot['today'] == {'date': '2026-11-18', 'uv': 2, 'pv': 3}
    assert len(snapshot['daily']) == 7 and snapshot['daily'][-2]['uv'] is None

    clock[0] = MIDNIGHT + timedelta(seconds=10)
    submit(first, 'heartbeat')
    snapshot = client.get(SUMMARY + '?days=30').json()['data']
    assert len(snapshot['daily']) == 30
    assert snapshot['online'] == 2 and snapshot['total_pv'] == 3
    assert snapshot['today'] == {'date': '2026-11-19', 'uv': 1, 'pv': 0}

    clock[0] = MIDNIGHT + timedelta(seconds=45)
    assert client.get(SUMMARY).json()['data']['online'] == 1
    clock[0] = MIDNIGHT + timedelta(seconds=70)
    assert client.get(SUMMARY).json()['data']['online'] == 0

    clock[0] += timedelta(days=3)
    with factory.begin() as db:
        visits.prune_activity(db, clock[0])
        assert db.scalar(select(func.count()).select_from(VisitVisitorDay)) == 0
    snapshot = client.get(SUMMARY).json()['data']
    assert snapshot['daily'][-2]['pv'] == 0 and snapshot['total_pv'] == 3


@pytest.mark.parametrize('dialect', ['sqlite', 'postgresql'])
def test_visits_concurrent_and_rolled_back(tmp_path, dialect):
    if dialect == 'postgresql':
        url = os.getenv('VISITS_POSTGRES_TEST_URL')
        if not url:
            pytest.skip('requires an isolated PostgreSQL database')
        assert url.rsplit('/', 1)[-1] == 'gduf_visit_stats_test'
    else:
        url = 'sqlite:///' + (tmp_path / 'parallel.db').as_posix()

    engine = create_engine(url)
    tables = [VisitVisitorDay.__table__, VisitDailyTotal.__table__]
    Base.metadata.create_all(engine, tables=tables, checkfirst=False)
    factory = sessionmaker(engine)
    group = Barrier(4)
    event = visits.VisitEvent(visitor_id=uuid4(), kind='page_view')
    stamp = MIDNIGHT + timedelta(seconds=2)

    def submit(offset):
        group.wait(timeout=5)
        with factory.begin() as db:
            visits.record_visit(db, stamp + timedelta(seconds=offset), event)

    try:
        with ThreadPoolExecutor(max_workers=4) as executor:
            list(executor.map(submit, range(4)))
        with pytest.raises(RuntimeError):
            with factory.begin() as db:
                visits.record_visit(db, stamp, visits.VisitEvent(visitor_id=uuid4(), kind='page_view'))
                raise RuntimeError('rollback')
        with factory() as db:
            clock = stamp + timedelta(seconds=3)
            totals = visits.read_summary(db, clock, date(2026, 11, 18), 7)
            assert (totals.today.uv, totals.today.pv, totals.online) == (1, 4, 1)
            latest = db.scalar(select(VisitVisitorDay.last_seen_at))
            assert latest.replace(tzinfo=timezone.utc) == clock
    finally:
        Base.metadata.drop_all(engine, tables=tables)
        engine.dispose()
