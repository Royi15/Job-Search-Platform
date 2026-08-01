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
    generate_notebook,
    grade_interview,
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
        grade_interview,
        generate_notebook,
    ]
    cron_jobs = [
        # Hourly on the hour, 09:00-17:00 server-local time (VM timezone is
        # Asia/Jerusalem), Sunday-Thursday only — the Israeli work week; Fri/Sat
        # scrapes would mostly burn Bright Data credits on an empty market, and
        # the 24h search window means Sunday 09:00 catches weekend postings.
        # Trimmed from 09:00-18:00 to cut Bright Data usage after cost review.
        # Python weekday numbering: Mon=0 ... Fri=4, Sat=5, Sun=6.
        # unique=True prevents overlap if a run is slow.
        cron(
            fetch_and_notify,
            weekday={6, 0, 1, 2, 3},
            hour=set(range(9, 18)),
            minute={0},
            unique=True,
            timeout=600,
        ),
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 4          # LLM calls are I/O-bound; 4 concurrent is plenty
    # Room for a slow LLM call plus one retry, PLUS a large-audio upload to
    # Gemini's Files API ahead of it: upload_file() alone can take up to
    # ~360s worst case (300s transfer + up to 60s polling for processing),
    # and generation on a large document uses a 420s per-attempt timeout
    # (notebook.py's GENERATION_TIMEOUT_SECONDS, raised from 300s so a
    # genuinely long response has room to finish) with one retry — 840s
    # worst case. Together that's ~1200s before any extraction/DB overhead,
    # so this needs real headroom above it.
    job_timeout = 1800
    keep_result = 3600
