"""Job enqueue helper shared by bot, API, and scheduler."""

from __future__ import annotations

from typing import Any

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from lumi.config import get_settings
from lumi.logging import get_logger

log = get_logger(__name__)

_pool: ArqRedis | None = None


def redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(get_settings().redis_url)


async def get_queue() -> ArqRedis:
    global _pool
    if _pool is None:
        _pool = await create_pool(redis_settings())
    return _pool


async def enqueue_job(job_name: str, *args: Any, **kwargs: Any) -> str | None:
    """Enqueue an arq job; returns job id or None on failure (never raises)."""
    try:
        pool = await get_queue()
        job = await pool.enqueue_job(job_name, *args, **kwargs)
        return job.job_id if job else None
    except Exception:  # noqa: BLE001 — queue issues must not break the caller
        log.exception("failed to enqueue job", fields={"job": job_name})
        return None


async def close_queue() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
