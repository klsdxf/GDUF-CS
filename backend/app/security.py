import hashlib
import os
import secrets
from datetime import timedelta, timezone
from fastapi import Depends, HTTPException, Request
from starlette.datastructures import UploadFile
from sqlalchemy.orm import Session
from .db import AdminSession, db_transaction, now

def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()

def fail(code, message, status=422, details=None):
    raise HTTPException(status, {'code': code, 'message': message, 'details': details or {}})

def authenticated(request: Request, db: Session = db_transaction):
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


async def authorized_form(request: Request, session=Depends(authenticated)):
    # Declaring File/Form on the endpoint makes FastAPI read the body before auth.
    async with request.form(max_files=1, max_fields=1) as form:
        if not isinstance(form.get('file'), UploadFile):
            fail('VALIDATION', '请选择上传文件')
        yield form


def upload_schema(*, with_mode=False):
    fields={'file': {'type':'string','format':'binary'}}
    if with_mode:
        fields['mode']={'type':'string','enum':['create','update'],'default':'create'}
    return {'requestBody': {'required':True, 'content': {'multipart/form-data': {
        'schema': {'type':'object','properties':fields,'required':['file']}
    }}}}
