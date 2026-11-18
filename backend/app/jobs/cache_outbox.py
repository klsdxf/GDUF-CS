"""Redis recovery coordinator and cache outbox poller."""
import logging
import time
from datetime import timedelta
from uuid import uuid4

from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from ..db import RedisRuntimeState, Session, now
from ..infrastructure.outbox import process_pending
from ..infrastructure.redis_client import CONTROL, RUN_ID, client, key

logger = logging.getLogger(__name__)
BEGIN = RUN_ID + """
if run_id() ~= ARGV[1] then return 0 end
redis.call('HSET', KEYS[1], 'run_id', ARGV[1], 'epoch', ARGV[2],
           'generation', ARGV[2], 'ready', 0, 'login_until', millis() + 300000)
return redis.call('HGET', KEYS[1], 'login_until')
"""
FINISH = RUN_ID + """
if run_id() ~= ARGV[1] or redis.call('HGET', KEYS[1], 'epoch') ~= ARGV[2] then return 0 end
redis.call('HSET', KEYS[1], 'ready', 1)
return 1
"""


def maintain(redis):
    instance = redis.info('server')['run_id']
    control = key(CONTROL)
    run, epoch, generation, login_until, ready = redis.hmget(
        control, 'run_id', 'epoch', 'generation', 'login_until', 'ready')
    if run == instance.encode() and epoch and generation and login_until and ready == b'1':
        process_pending()
        return
    # Compose runs one worker. The database lock protects an overlapping replacement.
    with Session.begin() as db:
        state = db.scalar(select(RedisRuntimeState).where(RedisRuntimeState.id == 1).with_for_update())
        if state is None:
            state = RedisRuntimeState(id=1)
            db.add(state)
        if (run != instance.encode() or not epoch or not generation or not login_until
                or state.run_id != instance or not state.epoch or epoch != state.epoch.encode()):
            state.run_id = instance
            state.epoch = uuid4().hex
            state.login_blocked_until = now() + timedelta(seconds=300)
            if not redis.eval(BEGIN, 1, control, instance, state.epoch):
                raise RedisError('Redis restarted while initializing control')
        recovery_epoch = state.epoch
    # Bound each recovery batch. New writes remain covered by the outbox and short TTL.
    count = process_pending(during_recovery=True)
    if count is not None and 0 <= count < 100:
        if not redis.eval(FINISH, 1, control, instance, recovery_epoch):
            raise RedisError('Redis restarted during recovery')


def main():
    logging.basicConfig(level=logging.INFO)
    redis = client()
    if redis is None:
        raise SystemExit('REDIS_URL is required')
    while True:
        try:
            maintain(redis)
            time.sleep(0.2)
        except (RedisError, SQLAlchemyError) as exc:
            logger.warning('cache_worker_retry: %s', type(exc).__name__)
            time.sleep(1)


if __name__ == '__main__':
    main()
