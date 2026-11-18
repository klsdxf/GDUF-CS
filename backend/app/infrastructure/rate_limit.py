"""Reserve a login attempt across API processes and refund only its own ticket."""
import hashlib
import hmac
import math
import os
from uuid import uuid4

from fastapi import Request
from redis.exceptions import RedisError

from .redis_client import CONTROL, RUN_ID, client, key
from .metrics import event
from ..security import fail

WINDOW = 300_000
RESERVE = RUN_ID + """
if not ready(KEYS[1]) then return {-1, 1000} end
local now = millis()
local until_ms = tonumber(redis.call('HGET', KEYS[1], 'login_until'))
if now < until_ms then return {-1, until_ms - now} end
local memory = redis.call('INFO', 'memory')
local maximum = tonumber(memory:match('maxmemory:(%d+)'))
if maximum > 0 and tonumber(memory:match('used_memory:(%d+)')) + 4096 >= maximum then
  return {-1, 1000}
end
redis.call('ZREMRANGEBYSCORE', KEYS[2], '-inf', now - tonumber(ARGV[2]))
if redis.call('ZCARD', KEYS[2]) >= 10 then
  local oldest = redis.call('ZRANGE', KEYS[2], 0, 0, 'WITHSCORES')
  return {0, tonumber(oldest[2]) + tonumber(ARGV[2]) - now}
end
redis.call('ZADD', KEYS[2], now, ARGV[1])
redis.call('PEXPIRE', KEYS[2], ARGV[2])
return {1, 0}
"""
REFUND = RUN_ID + """
if not ready(KEYS[1]) then return -1 end
return redis.call('ZREM', KEYS[2], ARGV[1])
"""


def unavailable(wait_ms=1000):
    event('login_unavailable')
    fail('LOGIN_UNAVAILABLE', '登录暂不可用，请稍后重试', 503,
         headers={'Retry-After': str(max(1, math.ceil(wait_ms / 1000)))})


class RedisLoginLimiter:
    def reserve(self, source):
        redis = client()
        secret = os.getenv('LOGIN_SOURCE_SECRET')
        if redis is None or not secret:
            unavailable()
        redis_key = key('limit:login:' + hmac.new(secret.encode(), source.encode(), hashlib.sha256).hexdigest())
        attempt = uuid4().hex
        try:
            result, wait = redis.eval(RESERVE, 2, key(CONTROL), redis_key, attempt, WINDOW)
        except RedisError:
            unavailable()
        if result == -1:
            unavailable(wait)
        if result == 0:
            event('login_limited')
            fail('RATE_LIMIT', '登录过于频繁，请稍后重试', 429,
                 headers={'Retry-After': str(max(1, math.ceil(wait / 1000)))})
        return redis_key, attempt

    def refund(self, ticket):
        redis_key, attempt = ticket
        try:
            if client().eval(REFUND, 2, key(CONTROL), redis_key, attempt) < 0:
                unavailable()
        except RedisError:
            unavailable()


def login_limiter(request: Request):
    return RedisLoginLimiter()
