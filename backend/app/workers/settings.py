"""ARQ worker configuration — run with:  arq app.workers.settings.WorkerSettings

One process handles both the task queue (resume parsing, AI generations) and
the cron schedule (job fetching), which matters on a 1 GiB VM.
"""
from arq import cron
from arq.connections import RedisSettings
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.workers.tasks import (
    deliver_pending_alerts,
    fetch_and_notify,
    match_preference,
    parse_resume,
    run_generation,
)


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
    functions = [
        parse_resume,
        run_generation,
        fetch_and_notify,
        match_preference,
        deliver_pending_alerts,
    ]
    cron_jobs = [
        # Hourly on the hour, 09:00-18:00 server-local time (VM timezone is
        # Asia/Jerusalem), Sunday-Thursday only — the Israeli work week; Fri/Sat
        # scrapes would mostly burn Bright Data credits on an empty market, and
        # the 24h search window means Sunday 09:00 catches weekend postings.
        # Python weekday numbering: Mon=0 ... Fri=4, Sat=5, Sun=6.
        # unique=True prevents overlap if a run is slow.
        cron(
            fetch_and_notify,
            weekday={6, 0, 1, 2, 3},
            hour=set(range(9, 19)),
            minute={0},
            unique=True,
            timeout=600,
        ),
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 4          # LLM calls are I/O-bound; 4 concurrent is plenty
    job_timeout = 600     # room for a slow LLM call plus one retry
    keep_result = 3600
