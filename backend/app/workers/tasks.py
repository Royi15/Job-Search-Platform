"""Background tasks. Everything slow lives here, not in the API process.

Each task opens its own DB session (ctx["db_factory"] is created once per
worker in settings.py) and reuses the same services/ code the API uses.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AIGeneration,
    GenerationKind,
    Job,
    JobAlert,
    Resume,
    SearchPreference,
    User,
)
from app.services import cover_letter, discord, tailoring
from app.services import telegram as tg
from app.services.ats_parser import (
    extract_pdf_text,
    extract_skills_llm,
    parse_resume_text,
)
from app.services.job_sources import FetchedJob, get_active_sources
from app.services.matching import job_matches_preference

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Resume parsing (enqueued by POST /resumes)
# ---------------------------------------------------------------------------
async def parse_resume(ctx: dict, resume_id: int) -> None:
    async with ctx["db_factory"]() as db:
        resume = await db.get(Resume, resume_id)
        if resume is None:
            return
        try:
            # pypdf is CPU-bound — keep the worker's event loop responsive.
            text = await asyncio.to_thread(extract_pdf_text, resume.storage_path)
            resume.raw_text = text
            extracted = parse_resume_text(text)  # regex: contacts, sections + dict skills
            try:
                extracted["skills"] = await extract_skills_llm(text)
                extracted["skills_source"] = "ai"
            except Exception:
                # LLM down/quota — keep the dictionary scan rather than failing
                logger.warning(
                    "LLM skill extraction failed for resume %s — using dictionary",
                    resume_id, exc_info=True,
                )
                extracted["skills_source"] = "dictionary"
            resume.extracted = extracted
            resume.parse_status = "done"
        except Exception:
            logger.exception("Failed to parse resume %s", resume_id)
            resume.parse_status = "failed"
        await db.commit()


# ---------------------------------------------------------------------------
# AI generations (enqueued by POST /ai/tailor and /ai/cover-letter)
# ---------------------------------------------------------------------------
async def run_generation(ctx: dict, generation_id: int) -> None:
    async with ctx["db_factory"]() as db:
        generation = await db.get(AIGeneration, generation_id)
        if generation is None:
            return
        resume = await db.get(Resume, generation.resume_id) if generation.resume_id else None
        if resume is None or not resume.raw_text:
            generation.status = "failed"
            generation.error = "Resume text unavailable"
            await db.commit()
            return

        generation.status = "running"
        await db.commit()
        try:
            if generation.kind == GenerationKind.RESUME_TAILORING:
                result = await tailoring.tailor_resume(
                    resume.raw_text, generation.job_description
                )
            else:
                result = await cover_letter.generate_outreach(
                    generation.kind, resume.raw_text, generation.job_description
                )
            generation.result = result
            generation.status = "done"
        except Exception as exc:
            logger.exception("Generation %s failed", generation_id)
            generation.status = "failed"
            # Include the exception class: str() of timeouts etc. is often ""
            generation.error = f"{type(exc).__name__}: {exc}"[:500].strip(": ")
        generation.completed_at = datetime.now(timezone.utc)
        await db.commit()


# ---------------------------------------------------------------------------
# Job fetch + fan-out (cron, every 15 minutes)
# ---------------------------------------------------------------------------
async def _upsert_jobs(db: AsyncSession, fetched: list[FetchedJob]) -> list[Job]:
    """Insert new jobs; ON CONFLICT skips ones we've already seen.
    Returns only the newly inserted rows."""
    new_jobs: list[Job] = []
    for item in fetched:
        stmt = (
            pg_insert(Job)
            .values(
                source=item.source,
                external_id=item.external_id,
                title=item.title,
                company=item.company,
                location=item.location,
                is_remote=item.is_remote,
                url=item.url,
                description=item.description,
                posted_at=item.posted_at,
            )
            .on_conflict_do_nothing(index_elements=["source", "external_id"])
            .returning(Job.id)
        )
        inserted_id = await db.scalar(stmt)
        if inserted_id is not None:
            new_jobs.append(await db.get(Job, inserted_id))
    await db.commit()
    return new_jobs


async def _broadcast_to_discord(db: AsyncSession, jobs: list[Job]) -> None:
    """Community firehose: every new student job goes to the Discord channel."""
    for job in jobs:
        if await discord.broadcast_job(job):
            job.discord_notified_at = datetime.now(timezone.utc)
            await db.commit()
        await asyncio.sleep(2)  # stay under Discord's 30 req/min webhook limit


async def _notify_matching_users(db: AsyncSession, jobs: list[Job]) -> None:
    """Personal alerts: match each new job against active preferences."""
    prefs = (
        await db.scalars(
            select(SearchPreference).where(SearchPreference.is_active.is_(True))
        )
    ).all()

    for job in jobs:
        matched_users: dict[int, int] = {}  # user_id -> preference_id
        for pref in prefs:
            if pref.user_id not in matched_users and job_matches_preference(job, pref):
                matched_users[pref.user_id] = pref.id

        for user_id, pref_id in matched_users.items():
            # UNIQUE(user_id, job_id) makes re-runs safe: no duplicate alerts.
            alert_id = await db.scalar(
                pg_insert(JobAlert)
                .values(user_id=user_id, job_id=job.id, preference_id=pref_id)
                .on_conflict_do_nothing(index_elements=["user_id", "job_id"])
                .returning(JobAlert.id)
            )
            if alert_id is None:
                continue
            user = await db.get(User, user_id)
            if user and user.telegram_chat_id:
                if await tg.send_message(user.telegram_chat_id, tg.format_job_alert(job)):
                    alert = await db.get(JobAlert, alert_id)
                    alert.notified_at = datetime.now(timezone.utc)
        await db.commit()


async def match_preference(ctx: dict, preference_id: int) -> str:
    """Backfill: when a preference is created or re-activated, immediately
    check it against recently fetched jobs — otherwise the user waits in
    silence until the next genuinely new posting happens to match."""
    async with ctx["db_factory"]() as db:
        pref = await db.get(SearchPreference, preference_id)
        if pref is None or not pref.is_active:
            return "preference missing or inactive"
        user = await db.get(User, pref.user_id)
        cutoff = datetime.now(timezone.utc) - timedelta(days=3)
        jobs = (
            await db.scalars(select(Job).where(Job.first_seen_at >= cutoff))
        ).all()

        created = 0
        for job in jobs:
            if not job_matches_preference(job, pref):
                continue
            alert_id = await db.scalar(
                pg_insert(JobAlert)
                .values(user_id=pref.user_id, job_id=job.id, preference_id=pref.id)
                .on_conflict_do_nothing(index_elements=["user_id", "job_id"])
                .returning(JobAlert.id)
            )
            if alert_id is None:
                continue  # already alerted for this job
            created += 1
            if user and user.telegram_chat_id:
                if await tg.send_message(user.telegram_chat_id, tg.format_job_alert(job)):
                    alert = await db.get(JobAlert, alert_id)
                    alert.notified_at = datetime.now(timezone.utc)
        await db.commit()
        logger.info("match_preference(%s): %d new alerts", preference_id, created)
        return f"matched={created}"


async def fetch_and_notify(ctx: dict) -> str:
    """Cron entry point: pull fresh jobs, then fan out (Discord + Telegram)."""
    fetched: list[FetchedJob] = []
    for source in get_active_sources():
        try:
            batch = await source.fetch_recent()
            fetched.extend(batch)
            logger.info("%s: fetched %d postings", source.name, len(batch))
        except Exception:
            logger.exception("Source %s failed — continuing with others", source.name)

    async with ctx["db_factory"]() as db:
        new_jobs = await _upsert_jobs(db, fetched)
        if new_jobs:
            await _broadcast_to_discord(db, new_jobs)
            await _notify_matching_users(db, new_jobs)

    summary = f"fetched={len(fetched)} new={len(new_jobs)}"
    logger.info("fetch_and_notify done: %s", summary)
    return summary
