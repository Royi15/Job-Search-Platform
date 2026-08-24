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
    generate_more_questions,
    generate_notebook,
    generate_quiz,
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
        generate_quiz,
        generate_more_questions,
    ]
    cron_jobs = (
        [
            # Every 3 hours, 09:00-18:00 server-local time (VM timezone is
            # Asia/Jerusalem), Sunday-Thursday only — the Israeli work week; Fri/Sat
            # scrapes would mostly burn Bright Data credits on an empty market, and
            # the 24h search window means Sunday 09:00 catches weekend postings.
            # Trimmed from hourly to every 3h to cut Bright Data usage further.
            # Python weekday numbering: Mon=0 ... Fri=4, Sat=5, Sun=6.
            # unique=True prevents overlap if a run is slow.
            cron(
                fetch_and_notify,
                weekday={6, 0, 1, 2, 3},
                hour={9, 12, 15, 18},
                minute={0},
                unique=True,
                timeout=600,
            ),
        ]
        if get_settings().enable_job_scraping_cron
        # Disabled (e.g. local dev, backend/.env has
        # ENABLE_JOB_SCRAPING_CRON=false): fetch_and_notify is still in
        # `functions` above, so it stays triggerable on demand via
        # `python -m scripts.trigger_fetch` — this only turns off the
        # automatic hourly schedule.
        else []
    )
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 4          # LLM calls are I/O-bound; 4 concurrent is plenty
    # Room for a slow LLM call plus one retry, PLUS a large-audio upload to
    # Gemini's Files API ahead of it. Worst case is now an MP3 quiz upload
    # (Trivisum): upload_file() up to ~360s (300s transfer + up to 60s
    # polling), THEN a transcription call — quiz.py's
    # TRANSCRIPTION_TIMEOUT_SECONDS=420s per attempt, one retry, 840s worst
    # case — THEN the questions-JSON generation itself from that
    # transcript — quiz.py's GENERATION_TIMEOUT_SECONDS=300s per attempt,
    # one retry, 600s worst case. Sequential total: 360 + 840 + 600 =
    # 1800s, before any extraction/DB overhead, so this needs real headroom
    # above it. (Notebook generation's own worst case — upload + a single
    # 420s-per-attempt generation, no separate transcription step — stays
    # comfortably inside this same budget.)
    job_timeout = 2700
    keep_result = 3600
