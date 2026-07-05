"""Manually enqueue one fetch_and_notify run instead of waiting for the
hourly cron — useful for testing the live pipeline end to end.

Usage (from backend/, venv active):  python -m scripts.trigger_fetch
Then watch it run:                   journalctl -u jobsearch-worker -f
"""
import asyncio

from arq import create_pool
from arq.connections import RedisSettings

from app.core.config import get_settings


async def main() -> None:
    redis = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    job = await redis.enqueue_job("fetch_and_notify")
    print(f"queued fetch_and_notify (job id: {job.job_id})")
    print("watch progress with:  journalctl -u jobsearch-worker -f")
    await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
