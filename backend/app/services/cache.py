import hashlib
import secrets
from contextlib import contextmanager

from fastapi import HTTPException
from redis import Redis
from redis.exceptions import RedisError

from app.config import get_settings

redis = Redis.from_url(get_settings().redis_url, decode_responses=True, socket_timeout=2)

# Increment and attach TTL in one atomic operation; a crash cannot leave an immortal counter.
COUNTER = """
local n = redis.call('INCR', KEYS[1])
if n == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
return n
"""
BUDGET = """
local m = tonumber(redis.call('GET', KEYS[1]) or '0')
local d = tonumber(redis.call('GET', KEYS[2]) or '0')
if m >= tonumber(ARGV[1]) or d >= tonumber(ARGV[2]) then return 0 end
redis.call('INCR', KEYS[1]); redis.call('EXPIRE', KEYS[1], 60)
redis.call('INCR', KEYS[2]); redis.call('EXPIRE', KEYS[2], 86400)
return 1
"""
UNLOCK = "if redis.call('GET',KEYS[1]) == ARGV[1] then return redis.call('DEL',KEYS[1]) end return 0"


def metric(name: str, count: int = 1) -> None:
    try:
        redis.hincrby("metrics", name, count)
    except RedisError:
        pass


def limit(scope: str, identifier: str, maximum: int, seconds: int) -> None:
    key = hashlib.sha256(identifier.encode()).hexdigest()
    try:
        if int(redis.eval(COUNTER, 1, f"rate:{scope}:{key}", seconds)) > maximum:
            raise HTTPException(429, "Too many attempts. Try again later.", headers={"Retry-After": str(seconds)})
    except RedisError as exc:
        # Authentication abuse protection must not silently disappear during an outage.
        raise HTTPException(503, "Authentication temporarily unavailable") from exc


@contextmanager
def lease(key: str, seconds: int = 30):
    token = secrets.token_urlsafe(24)
    acquired = False
    try:
        acquired = bool(redis.set(key, token, nx=True, ex=seconds))
        yield acquired
    finally:
        if acquired:
            try:
                redis.eval(UNLOCK, 1, key, token)
            except RedisError:
                pass
