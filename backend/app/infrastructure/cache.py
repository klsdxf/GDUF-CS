"""Cache only validated, public DTOs. Fixed slots bound payload and key count."""
import hashlib
import json
import os
import time
from threading import BoundedSemaphore
from uuid import uuid4

from fastapi.encoders import jsonable_encoder
from redis.exceptions import RedisError

from .redis_client import CONTROL, RUN_ID, client, key
from .metrics import event
from ..security import fail

SLOTS = 128
MAX_PAYLOAD = 256 * 1024
TTL_MS = 2000
slots = BoundedSemaphore(int(os.getenv('PUBLIC_DB_CONCURRENCY', '4')))
_retry_after = 0.0

READ = RUN_ID + """
if not ready(KEYS[1]) then return {0} end
local generation = redis.call('HGET', KEYS[1], 'generation')
local value = redis.call('GET', KEYS[2])
local tag = generation .. ':' .. ARGV[1] .. ':'
if value and value:sub(1, #tag) == tag then
  return {1, value:sub(#tag + 1)}
end
return {2, generation, millis()}
"""

FILL = RUN_ID + """
if not ready(KEYS[1]) or redis.call('HGET', KEYS[1], 'generation') ~= ARGV[1]
   or redis.call('GET', KEYS[3]) ~= ARGV[2] then return 0 end
local ttl = tonumber(ARGV[3]) - millis()
if ttl <= 0 then return 0 end
local used = tonumber(redis.call('INFO', 'memory'):match('used_memory:(%d+)'))
local maximum = tonumber(redis.call('INFO', 'memory'):match('maxmemory:(%d+)'))
if maximum > 0 and used + #ARGV[4] > maximum * 0.75 then return 0 end
redis.call('SET', KEYS[2], ARGV[4], 'PX', ttl)
return 1
"""

RELEASE = """
if redis.call('GET', KEYS[1]) == ARGV[1] then return redis.call('DEL', KEYS[1]) end
return 0
"""


def bounded_load(load):
    if not slots.acquire(timeout=0.1):
        event('public_rejected')
        fail('PUBLIC_BUSY', '公开查询繁忙，请稍后重试', 503, headers={'Retry-After': '1'})
    try:
        event('public_db_read')
        return load()
    finally:
        slots.release()


def cached(route, parameters, load):
    global _retry_after
    redis = client()
    if redis is None or time.monotonic() < _retry_after or os.getenv('PUBLIC_CACHE_DISABLED') == '1':
        return bounded_load(load)

    digest = hashlib.sha256(json.dumps([route, parameters], sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    control = key(CONTROL)
    slot = int(digest[:8], 16) % SLOTS
    data_key, lease_key = key(f'cache:{slot}'), key(f'lease:{slot}')
    owner = uuid4().hex
    try:
        result = redis.eval(READ, 2, control, data_key, digest)
        if result[0] == 1:
            event('cache_hit')
            return json.loads(result[1])
        if result[0] != 2:
            return bounded_load(load)
        acquired = redis.set(lease_key, owner, nx=True, px=1000)
        if not acquired:
            deadline = time.monotonic() + 0.1
            while time.monotonic() < deadline:
                time.sleep(0.02)
                result = redis.eval(READ, 2, control, data_key, digest)
                if result[0] == 1:
                    event('cache_hit')
                    return json.loads(result[1])
                if result[0] != 2:
                    break
            return bounded_load(load)
    except RedisError:
        event('cache_error')
        _retry_after = time.monotonic() + 1
        return bounded_load(load)

    try:
        value = bounded_load(load)
        body = json.dumps(jsonable_encoder(value), ensure_ascii=False, separators=(',', ':')).encode()
        generation = result[1]
        if len(body) <= MAX_PAYLOAD:
            try:
                redis.eval(FILL, 3, control, data_key, lease_key, generation, owner,
                           result[2] + TTL_MS, generation + b':' + digest.encode() + b':' + body)
            except RedisError:
                event('cache_error')
                _retry_after = time.monotonic() + 1
        return value
    finally:
        try:
            redis.eval(RELEASE, 1, lease_key, owner)
        except RedisError:
            _retry_after = time.monotonic() + 1
