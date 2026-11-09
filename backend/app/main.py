import os
import secrets
import asyncio
import time
from datetime import timedelta
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import FastAPI, Depends, Request, Response, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy import select, delete, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .db import Admin, AdminSession, db_session, now
from .security import authenticated, digest, fail
from .schemas import Login, PasswordChange

app = FastAPI(title='广金主场 API', version='1.0.0')
public_cache = {}
public_locks = {}

@app.middleware('http')
async def read_cache(request, call_next):
    path=request.url.path
    if request.method=='GET' and path.startswith('/api/v1/') and '/admin/' not in path and not path.endswith('/health'):
        key=str(request.url)
        if len(public_locks)>512:
            public_locks.clear()
        lock=public_locks.setdefault(key,asyncio.Lock())
        async with lock:
            cached=public_cache.get(key)
            if cached and cached[0]>time.monotonic():return Response(cached[1],media_type='application/json')
            response=await call_next(request)
            if response.status_code==200:
                body=b''.join([part async for part in response.body_iterator])
                if len(public_cache)>512:public_cache.clear()
                public_cache[key]=(time.monotonic()+2,body)
                return Response(body,status_code=200,headers=dict(response.headers))
            return response
    response=await call_next(request)
    if request.method not in ('GET','HEAD') and '/admin/' in path and response.status_code<300:
        public_cache.clear()
    return response
ph = PasswordHasher()
login_attempts = {}

@app.exception_handler(HTTPException)
async def http_error(request, exc):
    detail = exc.detail if isinstance(exc.detail, dict) else {'code': 'HTTP_ERROR', 'message': exc.detail}
    return JSONResponse({'error': {**detail, 'request_id': secrets.token_hex(8)}}, status_code=exc.status_code)

@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    return JSONResponse({'error': {'code': 'VALIDATION', 'message': '字段格式错误', 'details': str(exc), 'request_id': secrets.token_hex(8)}}, status_code=422)

@app.exception_handler(IntegrityError)
async def integrity_error(request, exc):
    return JSONResponse({'error': {'code': 'CONFLICT', 'message': '数据冲突，请刷新后重试', 'request_id': secrets.token_hex(8)}}, status_code=409)

@app.middleware('http')
async def private_headers(request, call_next):
    response = await call_next(request)
    if '/admin/' in request.url.path:
        response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response

@app.get('/api/v1/health')
def health(db: Session = Depends(db_session)):
    db.execute(text('SELECT 1'))
    return {'data': {'status': 'ok'}}

@app.post('/api/v1/admin/auth/login')
def login(payload: Login, request: Request, response: Response, db: Session = Depends(db_session)):
    payload=payload.model_dump()
    if request.headers.get('origin') != os.getenv('PUBLIC_ORIGIN', 'http://localhost:5173'):
        fail('ORIGIN', '请求来源不符', 403)
    ip = request.client.host
    attempts = [t for t in login_attempts.get(ip, []) if t > now().timestamp() - 300]
    if len(attempts) >= 10:
        fail('RATE_LIMIT', '登录过于频繁，五分钟后重试', 429)
    attempts.append(now().timestamp())
    login_attempts[ip] = attempts
    admin = db.get(Admin, 1)
    valid = False
    if admin and payload.get('username') == admin.username:
        try:
            valid = ph.verify(admin.password_hash, payload.get('password', ''))
        except VerifyMismatchError:
            pass
    if not valid:
        fail('INVALID_LOGIN', '账号或密码错误', 401)
    token, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
    db.add(AdminSession(token_hash=digest(token), csrf=csrf, expires_at=now() + timedelta(hours=12)))
    response.set_cookie('session', token, httponly=True, secure=os.getenv('ENV') == 'production', samesite='strict', max_age=43200)
    return {'data': {'username': admin.username, 'csrf': csrf}}

@app.get('/api/v1/admin/auth/me')
def me(session=Depends(authenticated), db: Session = Depends(db_session)):
    return {'data': {'username': db.get(Admin, 1).username, 'csrf': session.csrf}}

@app.post('/api/v1/admin/auth/logout')
def logout(response: Response, session=Depends(authenticated), db: Session = Depends(db_session)):
    db.delete(session)
    response.delete_cookie('session')
    return {'data': True}

from . import roster, tournaments, results, public, content, page_checks
for module in (roster, tournaments, results, public, content, page_checks):
    app.include_router(module.router)

from pathlib import Path
from fastapi.staticfiles import StaticFiles
media = Path(os.getenv('MEDIA_DIR', 'storage/media'))
media.mkdir(parents=True, exist_ok=True)
app.mount('/media', StaticFiles(directory=str(media)), name='media')

@app.put('/api/v1/admin/auth/password')
def password(payload: PasswordChange, session=Depends(authenticated), db: Session = Depends(db_session)):
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
