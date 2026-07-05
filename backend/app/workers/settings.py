"""ARQ worker configuration — run with:  arq app.workers.settings.WorkerSettings

One process handles both the task queue (resume parsing, AI generations) and
the cron schedule (job fetching), which matters on a 1 GiB VM.
"""
from arq import cron
from arq.connections import RedisSettings
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.workers.tasks import fetch_and_notify, parse_resume, run_generation


async def startup(ctx: dict) -> None:
    # The worker gets its own small engine — separate process, separate pool.
    ctx["engine"] = create_async_engine(
        get_settings().database_url, pool_size=3, max_overflow=2, pool_pre_ping=True
    )
    ctx["db_factory"] = async_sessionmaker(ctx["engine"], expire_on_commit=False)


async def shutdown(ctx: dict) -> None:
    await ctx["engine"].dispose()


class WorkerSettings:
    # fetch_and_notify is listed here too (not only in cron) so it can be
    # enqueued manually for testing: python -m scripts.trigger_fetch
    functions = [parse_resume, run_generation, fetch_and_notify]
    cron_jobs = [
        # Hourly: Bright Data bills per scraped record and the search window is
        # "Past 24 hours", so tighter polling only costs money — dedup by
        # job_posting_id means no duplicate notifications either way.
        # unique=True prevents overlap if a run is slow.
        cron(fetch_and_notify, minute={0}, unique=True, timeout=600),
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 4          # LLM calls are I/O-bound; 4 concurrent is plenty
    job_timeout = 300
    keep_result = 3600
