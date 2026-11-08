import hashlib
import os
import secrets
from datetime import timedelta, timezone
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session
from .db import AdminSession, db_session, now

def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()

def fail(code, message, status=422, details=None):
    raise HTTPException(status, {'code': code, 'message': message, 'details': details or {}})

def authenticated(request: Request, db: Session = Depends(db_session)):
    session = db.get(AdminSession, digest(request.cookies.get('session', '')))
    if not session or session.expires_at.replace(tzinfo=timezone.utc) <= now():
        fail('UNAUTHORIZED', '请登录管理员账号', 401)
    if request.method not in ('GET', 'HEAD'):
        origin = request.headers.get('origin')
        if origin != os.getenv('PUBLIC_ORIGIN', 'http://localhost:5173'):
            fail('ORIGIN', '请求来源不符', 403)
        if not secrets.compare_digest(request.headers.get('x-csrf-token', ''), session.csrf):
            fail('CSRF', '请刷新页面后重试', 403)
    return session
