from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from functools import lru_cache
from threading import Lock

from redis import Redis
from redis.exceptions import RedisError

from backend.app.core.config import settings


class QueueTimeoutError(RuntimeError):
    pass


class MemoryDailyQuota:
    def __init__(self) -> None:
        self._counts: dict[tuple[str, str], int] = {}
        self._lock = Lock()

    def consume(self, key: str, *, limit: int) -> bool:
        if limit <= 0:
            return False
        day = datetime.now(timezone.utc).date().isoformat()
        with self._lock:
            count = self._counts.get((day, key), 0) + 1
            self._counts[(day, key)] = count
        return count <= limit


class RedisDailyQuota:
    def consume(self, key: str, *, limit: int) -> bool:
        if limit <= 0:
            return False
        day = datetime.now(timezone.utc).date().isoformat()
        cache_key = f"chatbi:quota:{day}:{key}"
        client = Redis.from_url(
            settings.redis_url,
            socket_connect_timeout=0.5,
            socket_timeout=0.5,
        )
        try:
            with client.pipeline(transaction=True) as pipe:
                pipe.incr(cache_key)
                pipe.expire(cache_key, 48 * 3600)
                count, _ = pipe.execute()
            return int(count) <= limit
        except RedisError:
            # ponytail: fail open to preserve availability; add a circuit breaker
            # if quota bypass during Redis outages becomes a material risk.
            return True
        finally:
            client.close()


class AsyncConcurrencyGate:
    def __init__(self, *, limit: int, timeout_seconds: float) -> None:
        self._semaphore = asyncio.Semaphore(max(1, limit))
        self._timeout_seconds = max(0.01, timeout_seconds)

    @asynccontextmanager
    async def slot(self):
        try:
            async with asyncio.timeout(self._timeout_seconds):
                await self._semaphore.acquire()
        except TimeoutError as error:
            raise QueueTimeoutError("当前分析请求较多，请稍后重试") from error
        try:
            yield
        finally:
            self._semaphore.release()


@lru_cache(maxsize=1)
def get_daily_quota() -> MemoryDailyQuota | RedisDailyQuota:
    if settings.app_env == "production":
        return RedisDailyQuota()
    return MemoryDailyQuota()


@lru_cache(maxsize=1)
def get_gpu_gate() -> AsyncConcurrencyGate:
    return AsyncConcurrencyGate(
        limit=settings.qa_max_concurrency,
        timeout_seconds=settings.qa_queue_timeout_seconds,
    )
