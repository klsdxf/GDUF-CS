"""Durable public cache invalidation. Redis updates are idempotent by rotation."""
import logging
from datetime import timedelta
from uuid import uuid4

from redis.exceptions import RedisError
from sqlalchemy import event, select
from sqlalchemy.orm import Session as ORMSession

from .redis_client import CONTROL, RUN_ID, client, key
from ..db import (Advancement, Announcement, CacheInvalidation, Competition, LiveStream, Match,
                  Member, Registration, RosterSnapshot, Session, Stage, now, uid)

logger = logging.getLogger(__name__)
PUBLIC_MODELS = (Advancement, Announcement, Competition, LiveStream, Match,
                 Member, Registration, RosterSnapshot, Stage)
ROTATE = RUN_ID + """
if redis.call('HGET', KEYS[1], 'run_id') ~= run_id() then return 0 end
redis.call('HSET', KEYS[1], 'generation', ARGV[1])
return 1
"""


def mark_public_change(db):
    if 'public_invalidation' not in db.info:
        event_id = uid()
        db.info['public_invalidation'] = event_id
        db.add(CacheInvalidation(id=event_id))


@event.listens_for(ORMSession, 'after_transaction_end')
def forget_on_transaction_end(db, transaction):
    # Request sessions consume the id after commit. A reused transaction may create its own event.
    if transaction.parent is None:
        db.info['last_public_invalidation'] = db.info.pop('public_invalidation', None)


@event.listens_for(ORMSession, 'before_flush')
def capture_public_changes(db, context, instances):
    if any(isinstance(obj, PUBLIC_MODELS) for obj in (*db.new, *db.dirty, *db.deleted)):
        mark_public_change(db)


def process_pending(event_id=None, *, during_recovery=False):
    redis = client()
    if redis is None:
        return
    with Session.begin() as db:
        query = select(CacheInvalidation).where(CacheInvalidation.completed_at.is_(None))
        if event_id:
            query = query.where(CacheInvalidation.id == event_id)
        elif not during_recovery:
            query = query.where(CacheInvalidation.retry_at <= now())
        events = list(db.scalars(query.order_by(CacheInvalidation.retry_at, CacheInvalidation.id)
                                 .limit(100).with_for_update(skip_locked=True)))
        if not events:
            return 0
        try:
            if not redis.eval(ROTATE, 1, key(CONTROL), uuid4().hex):
                raise RedisError('control state unavailable')
        except RedisError as exc:
            for item in events:
                item.attempts += 1
                item.last_error = type(exc).__name__
                item.retry_at = now() + timedelta(seconds=min(30, 0.2 * (2 ** min(item.attempts, 8))))
            logger.warning('cache_invalidation_retry', extra={'error_type': type(exc).__name__})
            return -1
        for item in events:
            item.completed_at = now()
            item.last_error = None
        return len(events)


def try_after_commit(event_id):
    try:
        process_pending(event_id)
    except Exception:
        logger.exception('cache_invalidation_deferred')
