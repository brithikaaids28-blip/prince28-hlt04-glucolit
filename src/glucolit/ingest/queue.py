"""Redis queue helpers for GlucoLit ingestion jobs."""

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from glucolit.config import get_settings


async def get_queue() -> ArqRedis:
    """Create a Redis connection for the ingestion queue."""
    settings = get_settings()
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    return await create_pool(redis_settings)


async def enqueue_ingest(job_id: str) -> str:
    """Submit an ingestion job to the background worker."""
    redis = await get_queue()
    try:
        job = await redis.enqueue_job("process_ingest_job", job_id)
        if job is None:
            raise RuntimeError(f"Job {job_id} is already queued")
        return job.job_id
    finally:
        await redis.aclose()
