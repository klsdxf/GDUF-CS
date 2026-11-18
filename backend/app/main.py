from contextlib import asynccontextmanager
from datetime import timedelta
from ipaddress import ip_address
import logging
import os
import secrets
import socket

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import FastAPI, Depends, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError, OperationalError, TimeoutError as PoolTimeout
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException

from .db import Admin, AdminSession, CacheInvalidation, db_transaction, engine, now
from .infrastructure import outbox  # register database transaction listeners
from .infrastructure.rate_limit import login_limiter
from .infrastructure.redis_client import close, client as redis_client, key
from .infrastructure.request_context import RequestContext, request_id
from .security import authenticated, digest, fail
from .schemas import Login, PasswordChange
from .schemas_public import Data
from .schemas_responses import ErrorEnvelope, SessionData

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app):
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    try:
        yield
    finally:
        close()


app = FastAPI(title='广金主场 API', version='1.0.0', lifespan=lifespan,
              responses={422: {'model': ErrorEnvelope}})
app.add_middleware(RequestContext)
ph = PasswordHasher()

def login_source(request):
    peer = request.client.host
    forwarded = request.headers.get('x-forwarded-for')
    if not forwarded:
        return peer
    trusted = set()
    for entry in os.getenv('LOGIN_TRUSTED_PROXIES', '').split(','):
        entry = entry.strip()
        if not entry:
            continue
        try:
            trusted.add(str(ip_address(entry)))
        except ValueError:
            try:
                trusted.update(row[4][0] for row in socket.getaddrinfo(entry, None))
            except socket.gaierror:
                continue
    for hop in reversed(forwarded.split(',')):
        if peer not in trusted:
            break
        try:
            peer = str(ip_address(hop.strip()))
        except ValueError:
            break
    return peer




def error_response(status, code, message, details=None, headers=None):
    return JSONResponse(
        {'error': {'code': code, 'message': message, 'details': details if details is not None else {},
                   'request_id': request_id.get()}},
        status_code=status, headers=headers,
    )


@app.exception_handler(HTTPException)
async def http_error(request, exc):
    detail = exc.detail if isinstance(exc.detail, dict) else {'code': 'HTTP_ERROR', 'message': str(exc.detail)}
    return error_response(exc.status_code, detail['code'], detail['message'], detail.get('details'), exc.headers)


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    details = [{'path': [str(part) for part in item['loc']], 'code': item['type'],
                'message': '缺少必填字段' if item['type'] == 'missing' else '字段值不符合接口约定'}
               for item in exc.errors()]
    return error_response(422, 'VALIDATION', '字段格式错误', details)


@app.exception_handler(IntegrityError)
async def integrity_error(request, exc):
    return error_response(409, 'CONFLICT', '数据冲突，请刷新后重试')

@app.exception_handler(OperationalError)
@app.exception_handler(PoolTimeout)
async def database_error(request, exc):
    from .infrastructure.metrics import event
    sqlstate = getattr(getattr(exc, 'orig', None), 'sqlstate', None)
    code = {'55P03': 'DB_LOCK_TIMEOUT', '40P01': 'DB_DEADLOCK', '57014': 'DB_STATEMENT_TIMEOUT'}.get(
        sqlstate, 'DB_UNAVAILABLE')
    event(code.lower())
    logger.warning('database_request_unavailable', extra={'request_id': request_id.get(), 'error_code': code})
    return error_response(503, code, '数据库暂不可用，请稍后重试', headers={'Retry-After': '1'})


@app.get('/health/live', include_in_schema=False)
def live_health():
    return {'data': {'status': 'ok'}}


@app.get('/health/ready', include_in_schema=False)
@app.get('/api/v1/health')
def health(db: Session = db_transaction):
    db.execute(text('SELECT 1'))
    return {'data': {'status': 'ok'}}


@app.get('/internal/components', include_in_schema=False)
def components():
    from redis.exceptions import RedisError
    from .infrastructure.redis_client import CONTROL, RUN_ID
    redis = redis_client()
    state = 'unavailable'
    try:
        if redis is not None:
            state = redis.eval(RUN_ID + """
                if not ready(KEYS[1]) then return 'recovering' end
                local until_ms = tonumber(redis.call('HGET', KEYS[1], 'login_until'))
                if millis() < until_ms then return 'login_protected' end
                return 'ready'
            """, 1, key(CONTROL)).decode()
    except RedisError:
        pass
    return {'data': {'redis': state, 'new_login': state == 'ready'}}


@app.get('/internal/metrics', include_in_schema=False)
def metrics(db: Session = db_transaction):
    from time import monotonic
    from datetime import timezone
    from redis.exceptions import RedisError
    from .infrastructure.metrics import exposition

    lines = exposition()
    if hasattr(engine.pool, 'checkedout'):
        lines.append(f'gduf_db_pool_checked_out {engine.pool.checkedout()}')
    pending, oldest = db.execute(select(func.count(), func.min(CacheInvalidation.created_at))
                                 .where(CacheInvalidation.completed_at.is_(None))).one()
    if oldest and oldest.tzinfo is None:
        oldest = oldest.replace(tzinfo=timezone.utc)
    lines += [f'gduf_cache_outbox_pending {pending}',
              f'gduf_cache_outbox_oldest_seconds {(now() - oldest).total_seconds() if oldest else 0}']
    start = monotonic()
    try:
        redis = redis_client()
        if redis is not None:
            memory = redis.info('memory')
            stats = redis.info('stats')
            clients = redis.info('clients')
            lines.extend([
                'gduf_redis_up 1',
                f'gduf_redis_latency_seconds {monotonic() - start}',
                f'gduf_redis_used_bytes {memory["used_memory"]}',
                f'gduf_redis_max_bytes {memory["maxmemory"]}',
                f'gduf_redis_connected_clients {clients["connected_clients"]}',
                f'gduf_redis_error_replies_total {stats["total_error_replies"]}',
                f'gduf_new_login_ready {int(components()["data"]["new_login"])}',
            ])
        else:
            lines.append('gduf_redis_up 0')
    except RedisError:
        lines.append('gduf_redis_up 0')
    return Response('\n'.join(lines) + '\n', media_type='text/plain; version=0.0.4')

@app.post('/api/v1/admin/auth/login', response_model=Data[SessionData], responses={
    status: {'model': ErrorEnvelope} for status in (401, 403, 429, 503)
})
def login(payload: Login, request: Request, response: Response, limiter=Depends(login_limiter), db: Session = db_transaction):
    payload=payload.model_dump()
    if request.headers.get('origin') != os.getenv('PUBLIC_ORIGIN', 'http://localhost:5173'):
        fail('ORIGIN', '请求来源不符', 403)
    ip = login_source(request)
    attempt = limiter.reserve(ip)
    admin = db.get(Admin, 1)
    valid = False
    if admin and payload.get('username') == admin.username:
        try:
            valid = ph.verify(admin.password_hash, payload.get('password', ''))
        except VerifyMismatchError:
            pass
    if not valid:
        fail('INVALID_LOGIN', '账号或密码错误', 401)
    limiter.refund(attempt)
    token, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
    db.add(AdminSession(token_hash=digest(token), csrf=csrf, expires_at=now() + timedelta(hours=12)))
    response.set_cookie('session', token, httponly=True, secure=os.getenv('ENV') == 'production', samesite='strict', max_age=43200)
    return {'data': {'username': admin.username, 'csrf': csrf}}

@app.get('/api/v1/admin/auth/me', response_model=Data[SessionData])
def me(session=Depends(authenticated), db: Session = db_transaction):
    return {'data': {'username': db.get(Admin, 1).username, 'csrf': session.csrf}}

@app.post('/api/v1/admin/auth/logout')
def logout(response: Response, session=Depends(authenticated), db: Session = db_transaction):
    db.delete(session)
    response.delete_cookie('session')
    return {'data': True}

from . import roster, tournaments, results, public, content, page_checks, final_results, test_data, visits
for module in (roster, tournaments, results, public, content, page_checks, final_results, test_data, visits):
    app.include_router(module.router)

from pathlib import Path
from fastapi.staticfiles import StaticFiles
media = Path(os.getenv('MEDIA_DIR', 'storage/media'))
media.mkdir(parents=True, exist_ok=True)
app.mount('/media', StaticFiles(directory=str(media)), name='media')

@app.put('/api/v1/admin/auth/password')
def password(payload: PasswordChange, session=Depends(authenticated), db: Session = db_transaction):
    payload=payload.model_dump()
    admin = db.get(Admin, 1)
    try:
        ph.verify(admin.password_hash, payload.get('current_password', ''))
    except VerifyMismatchError:
        fail('PASSWORD', '当前密码错误', 403)
    if len(payload.get('password', '')) < 12:
        fail('PASSWORD', '新密码至少 12 位')
    admin.password_hash = ph.hash(payload['password'])
    db.execute(delete(AdminSession))
    return {'data': True}
