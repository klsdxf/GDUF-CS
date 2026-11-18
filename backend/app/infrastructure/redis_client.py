"""Shared Redis connection and scripts. The control state is fenced by Redis run_id."""
import os
from functools import lru_cache

from redis import Redis
from redis.backoff import NoBackoff
from redis.retry import Retry


@lru_cache
def client():
    url = os.getenv('REDIS_URL')
    if not url:
        return None
    return Redis.from_url(
        url, protocol=2, socket_connect_timeout=0.1, socket_timeout=0.1,
        max_connections=int(os.getenv('REDIS_MAX_CONNECTIONS', '16')),
        retry=Retry(NoBackoff(), 0),
    )


def key(suffix):
    return f"{os.getenv('REDIS_NAMESPACE', 'gduf:development:v1')}:{suffix}"


def close():
    if client.cache_info().currsize and client() is not None:
        client().close()
    client.cache_clear()


RUN_ID = """
local function run_id()
  return redis.call('INFO', 'server'):match('run_id:([%w]+)')
end
local function ready(control)
  return redis.call('HGET', control, 'run_id') == run_id()
     and redis.call('HGET', control, 'ready') == '1'
end
local function millis()
  local t = redis.call('TIME')
  return t[1] * 1000 + math.floor(t[2] / 1000)
end
"""
CONTROL = 'control'
