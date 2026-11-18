import os
from datetime import date, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, UUID4, ValidationError
from sqlalchemy import delete, distinct, func, select, true, update
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from .db import VisitDailyTotal, VisitVisitorDay, db_transaction, now
from .security import authenticated, digest, fail

SHANGHAI = ZoneInfo('Asia/Shanghai')
ONLINE_WINDOW = timedelta(seconds=60)
MAX_BODY_BYTES = 1024


class VisitEvent(BaseModel, extra='forbid'):
    visitor_id: UUID4
    kind: Literal['page_view', 'heartbeat']


class DailyStats(BaseModel):
    date: date
    uv: int | None
    pv: int | None


class VisitSummary(BaseModel):
    tracking_started_on: date | None
    as_of: datetime
    online: int | None = None
    today: DailyStats | None = None
    total_pv: int | None = None
    daily: list[DailyStats] = Field(default_factory=list)


class DisabledOrAccepted(BaseModel):
    data: None = None


class SummaryResponse(BaseModel):
    data: VisitSummary


router = APIRouter(prefix='/api/v1')


def tracking_start(today: date) -> date | None:
    configured = os.getenv('VISIT_STATS_START_DATE', '').strip()
    if not configured:
        return None
    try:
        start = date.fromisoformat(configured)
    except ValueError:
        fail('VISIT_STATS_CONFIGURATION', '访问统计启用日期配置无效', 503)
    return start if start <= today else None


async def read_event(request: Request) -> VisitEvent:
    if request.headers.get('origin') != os.getenv('PUBLIC_ORIGIN', 'http://localhost:5173'):
        fail('ORIGIN', '请求来源不符', 403)
    if request.headers.get('content-type', '').split(';', 1)[0].strip().lower() != 'application/json':
        fail('VISIT_CONTENT_TYPE', '仅接受 JSON 请求', 415)
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_BODY_BYTES:
            fail('VISIT_BODY_SIZE', '请求体超过大小上限', 413)
        body.extend(chunk)
    try:
        return VisitEvent.model_validate_json(body)
    except ValidationError:
        fail('VALIDATION', '访问事件字段格式错误')


def record_visit(db: Session, stamp: datetime, payload: VisitEvent) -> None:
    stat_date = stamp.astimezone(SHANGHAI).date()
    visitor = digest(str(payload.visitor_id))
    insert = postgres_insert if db.get_bind().dialect.name == 'postgresql' else sqlite_insert
    activity = insert(VisitVisitorDay).values(stat_date=stat_date, visitor_digest=visitor, last_seen_at=stamp)
    added = db.scalar(activity.on_conflict_do_nothing(index_elements=['stat_date', 'visitor_digest'])
                      .returning(VisitVisitorDay.stat_date))
    if added is None:
        db.execute(update(VisitVisitorDay).where(
            VisitVisitorDay.stat_date == stat_date,
            VisitVisitorDay.visitor_digest == visitor,
            VisitVisitorDay.last_seen_at < stamp,
        ).values(last_seen_at=stamp))

    uv = int(added is not None)
    pv = int(payload.kind == 'page_view')
    if uv or pv:
        totals = insert(VisitDailyTotal).values(stat_date=stat_date, uv=uv, pv=pv)
        db.execute(totals.on_conflict_do_update(index_elements=['stat_date'], set_={
            'uv': VisitDailyTotal.uv + totals.excluded.uv,
            'pv': VisitDailyTotal.pv + totals.excluded.pv,
        }))


def read_summary(db: Session, stamp: datetime, start: date | None, days: int) -> VisitSummary:
    summary = VisitSummary(tracking_started_on=start, as_of=stamp)
    if start is None:
        return summary
    today = stamp.astimezone(SHANGHAI).date()
    first_day = today - timedelta(days=days - 1)
    # Read all counters under the same database statement snapshot.
    active = select(func.count(distinct(VisitVisitorDay.visitor_digest)).label('online')).where(
        VisitVisitorDay.last_seen_at > stamp - ONLINE_WINDOW,
        VisitVisitorDay.last_seen_at <= stamp,
    ).subquery()
    totals = select(VisitDailyTotal).where(
        VisitDailyTotal.stat_date.between(max(first_day, start), today)
    ).subquery()
    rows = db.execute(select(active.c.online, totals.c.stat_date, totals.c.uv, totals.c.pv)
                      .select_from(active.outerjoin(totals, true()))).all()
    counts = {row.stat_date: (row.uv, row.pv) for row in rows if row.stat_date is not None}
    for offset in range(days):
        day = first_day + timedelta(days=offset)
        uv, pv = counts.get(day, (0, 0) if day >= start else (None, None))
        summary.daily.append(DailyStats(date=day, uv=uv, pv=pv))
    summary.online = rows[0].online
    summary.today = summary.daily[-1]
    summary.total_pv = sum(pv for _, pv in counts.values())
    return summary


def prune_activity(db: Session, stamp: datetime) -> None:
    earliest = stamp.astimezone(SHANGHAI).date() - timedelta(days=2)
    db.execute(delete(VisitVisitorDay).where(VisitVisitorDay.stat_date < earliest))


@router.post('/visits', response_model=DisabledOrAccepted, openapi_extra={
    'requestBody': {'required': True, 'content': {
        'application/json': {'schema': VisitEvent.model_json_schema()},
    }},
})
def collect_visit(payload: VisitEvent = Depends(read_event), db: Session = db_transaction):
    stamp = now()
    if tracking_start(stamp.astimezone(SHANGHAI).date()) is not None:
        record_visit(db, stamp, payload)
    return {'data': None}


@router.get('/admin/visits/summary', response_model=SummaryResponse, dependencies=[Depends(authenticated)])
def visit_summary(days: Literal['7', '30'] = '7', db: Session = db_transaction):
    stamp = now()
    return {'data': read_summary(db, stamp, tracking_start(stamp.astimezone(SHANGHAI).date()), int(days))}
