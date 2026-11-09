"""Uncached, read-only HTML existence checks for the web auth_request subrequest."""
import re
from urllib.parse import urlsplit, unquote
from fastapi import APIRouter, Depends, Header, HTTPException, Response
from sqlalchemy.orm import Session
from .db import db_session
from . import public

router = APIRouter()

@router.get('/internal/page-check', include_in_schema=False)
def page_check(x_original_uri: str = Header(default=''), db: Session = Depends(db_session)):
    path = unquote(urlsplit(x_original_uri).path)
    if '%' in path or '//' in path or any(p in ('.', '..') for p in path.split('/')):
        return Response(status_code=403)
    try:
        if path in ('/', '/competitions', '/announcements'):
            return Response(status_code=204)
        m = re.fullmatch(r'/(matches|announcements)/([^/]+)', path)
        if m:
            (public.match if m[1] == 'matches' else public.announcement)(m[2], db)
        else:
            m = re.fullmatch(r'/competitions/([^/]+)(?:/(schedule|standings|teams|rules|announcements|live)(?:/([^/]+))?)?', path)
            if not m or (m[3] and m[2] != 'teams'):
                return Response(status_code=403)
            if m[3]:
                public.team(m[1], m[3], db)
            else:
                public.public_c(db, m[1])
    except HTTPException as exc:
        if exc.status_code == 404:
            return Response(status_code=403)
        raise
    return Response(status_code=204)
