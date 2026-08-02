"""Background tasks. Everything slow lives here, not in the API process.

Each task opens its own DB session (ctx["db_factory"] is created once per
worker in settings.py) and reuses the same services/ code the API uses.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import undefer

from app.models import (
    AIGeneration,
    GenerationKind,
    InterviewSession,
    Job,
    JobAlert,
    Notebook,
    Quiz,
    Resume,
    SearchPreference,
    User,
)
from app.services import cover_letter, discord, tailoring
from app.services import interview as interview_engine
from app.services import notebook as notebook_engine
from app.services import quiz as quiz_engine
from app.services import telegram as tg
from app.services.ats_parser import (
    extract_pdf_text,
    extract_skills_llm,
    parse_resume_text,
)
from app.services.document_extract import extract_pptx_text
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
                await asyncio.sleep(1.1)  # respect Telegram's per-chat rate limit
        await db.commit()
        logger.info("match_preference(%s): %d new alerts", preference_id, created)
        return f"matched={created}"


async def grade_interview(ctx: dict, session_id: int) -> str:
    """Evaluate a finished interview transcript and store the report.
    Runs in the worker: it's the one heavyweight LLM call of the flow."""
    async with ctx["db_factory"]() as db:
        session = await db.get(InterviewSession, session_id)
        if session is None or session.status != "grading":
            return "session missing or not awaiting grading"

        resume_text = "(resume unavailable)"
        if session.resume_id:
            resume = await db.get(Resume, session.resume_id)
            if resume and resume.raw_text:
                resume_text = resume.raw_text

        try:
            session.report = await interview_engine.grade_transcript(
                resume_text, session.job_description, session.transcript, session.language
            )
            session.status = "done"
            session.stage = "done"
        except Exception as exc:
            logger.exception("Interview grading %s failed", session_id)
            session.report = {"error": f"{type(exc).__name__}: {exc}"[:500].strip(": ")}
            session.status = "failed"
        session.completed_at = datetime.now(timezone.utc)
        await db.commit()
        return f"graded session {session_id}: {session.status}"


async def deliver_pending_alerts(ctx: dict, user_id: int) -> str:
    """When a user links (or relinks) Telegram, push the alerts that matched
    while they weren't linked — the natural onboarding order is "create
    preference, then link", and without this the backfill matches land in
    that gap and the user stares at an empty chat assuming linking failed."""
    async with ctx["db_factory"]() as db:
        user = await db.get(User, user_id)
        if user is None or not user.telegram_chat_id:
            return "user missing or not linked"
        cutoff = datetime.now(timezone.utc) - timedelta(days=3)
        alerts = (
            await db.scalars(
                select(JobAlert)
                .where(
                    JobAlert.user_id == user_id,
                    JobAlert.notified_at.is_(None),
                    JobAlert.dismissed.is_(False),
                    JobAlert.matched_at >= cutoff,
                )
                .order_by(JobAlert.matched_at)
            )
        ).all()

        delivered = 0
        for alert in alerts:
            if await tg.send_message(user.telegram_chat_id, tg.format_job_alert(alert.job)):
                alert.notified_at = datetime.now(timezone.utc)
                delivered += 1
                await db.commit()  # commit per send: a crash loses nothing
            await asyncio.sleep(1.1)  # Telegram allows ~1 msg/sec per chat
        logger.info("deliver_pending_alerts(%s): %d delivered", user_id, delivered)
        return f"delivered={delivered}"


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


# ---------------------------------------------------------------------------
# Notebook generation (enqueued by POST /notebooks)
# ---------------------------------------------------------------------------
async def generate_notebook(ctx: dict, notebook_id: int) -> str:
    """Extract + summarize a source file into a structured notebook. The
    source file is deleted afterward either way — it's single-use, unlike a
    resume which gets re-read on every tailoring run."""
    async with ctx["db_factory"]() as db:
        nb = await db.get(Notebook, notebook_id)
        if nb is None:
            return "notebook missing"

        nb.status = "running"
        await db.commit()

        try:
            if nb.source_type == "pdf":
                text = await asyncio.to_thread(extract_pdf_text, nb.storage_path)
                content = await notebook_engine.generate_from_text(text, nb.language)
            elif nb.source_type == "pptx":
                text = await asyncio.to_thread(extract_pptx_text, nb.storage_path)
                content = await notebook_engine.generate_from_text(text, nb.language)
            elif nb.source_type == "mp3":
                audio_bytes = await asyncio.to_thread(Path(nb.storage_path).read_bytes)
                content = await notebook_engine.generate_from_audio(
                    audio_bytes, "audio/mpeg", nb.language
                )
            else:
                raise ValueError(f"Unsupported source_type: {nb.source_type}")

            nb.content = content
            nb.title = content.get("title") or nb.original_filename
            nb.status = "done"
        except Exception as exc:
            logger.exception("Notebook generation %s failed", notebook_id)
            nb.error = f"{type(exc).__name__}: {exc}"[:500].strip(": ")
            nb.status = "failed"
        finally:
            # Delete the source regardless of outcome — no orphaned uploads
            # piling up on the VM even if generation failed.
            if nb.storage_path:
                Path(nb.storage_path).unlink(missing_ok=True)
                nb.storage_path = None

        nb.completed_at = datetime.now(timezone.utc)
        final_status = nb.status
        try:
            await db.commit()
        except Exception as exc:
            # A failure here (bad byte sequence, oversized value, etc.)
            # would otherwise crash the task with the row already committed
            # at status="running" from earlier — wedging it there forever,
            # since nothing else would ever come back and retry it.
            logger.exception(
                "Notebook %s: final commit failed — marking failed instead "
                "of leaving it stuck", notebook_id,
            )
            await db.rollback()
            final_status = "failed"
            await db.execute(
                update(Notebook)
                .where(Notebook.id == notebook_id)
                .values(
                    status="failed",
                    error=f"Save failed: {type(exc).__name__}: {exc}"[:500].strip(": "),
                    content=None,
                    completed_at=datetime.now(timezone.utc),
                )
            )
            await db.commit()
        return f"notebook {notebook_id}: {final_status}"


# ---------------------------------------------------------------------------
# Quiz generation (enqueued by POST /quizzes)
# ---------------------------------------------------------------------------
async def generate_quiz(ctx: dict, quiz_id: int) -> str:
    """Extract/transcribe a source file and turn it into a multiple-choice
    quiz. The source file is deleted afterward either way — same
    single-use policy as notebooks."""
    async with ctx["db_factory"]() as db:
        quiz = await db.get(Quiz, quiz_id)
        if quiz is None:
            return "quiz missing"

        quiz.status = "running"
        await db.commit()

        try:
            if quiz.source_type == "pdf":
                text = await asyncio.to_thread(extract_pdf_text, quiz.storage_path)
            elif quiz.source_type == "pptx":
                text = await asyncio.to_thread(extract_pptx_text, quiz.storage_path)
            elif quiz.source_type == "mp3":
                audio_bytes = await asyncio.to_thread(Path(quiz.storage_path).read_bytes)
                text = await quiz_engine.transcribe_audio(audio_bytes, "audio/mpeg")
            else:
                raise ValueError(f"Unsupported source_type: {quiz.source_type}")
            # Kept (unlike the source file, which stays single-use) so
            # "generate more" can regenerate against the same source later
            # — a transcript for mp3, extracted text for pdf/pptx, treated
            # identically from here on.
            quiz.source_text = text
            quiz.questions = await quiz_engine.generate_quiz(text, quiz.difficulty, quiz.language)
            quiz.status = "done"
        except Exception as exc:
            logger.exception("Quiz generation %s failed", quiz_id)
            quiz.error = f"{type(exc).__name__}: {exc}"[:500].strip(": ")
            quiz.status = "failed"
        finally:
            if quiz.storage_path:
                Path(quiz.storage_path).unlink(missing_ok=True)
                quiz.storage_path = None

        quiz.completed_at = datetime.now(timezone.utc)
        final_status = quiz.status
        try:
            await db.commit()
        except Exception as exc:
            # Same rationale as generate_notebook's final-commit guard: a
            # save-time failure here would otherwise wedge the row at
            # status="running" forever with nothing to retry it.
            logger.exception(
                "Quiz %s: final commit failed — marking failed instead of "
                "leaving it stuck", quiz_id,
            )
            await db.rollback()
            final_status = "failed"
            await db.execute(
                update(Quiz)
                .where(Quiz.id == quiz_id)
                .values(
                    status="failed",
                    error=f"Save failed: {type(exc).__name__}: {exc}"[:500].strip(": "),
                    questions=None,
                    source_text=None,
                    completed_at=datetime.now(timezone.utc),
                )
            )
            await db.commit()
        return f"quiz {quiz_id}: {final_status}"


# ---------------------------------------------------------------------------
# Generate more quiz questions (enqueued by POST /quizzes/{id}/generate-more)
# ---------------------------------------------------------------------------
async def generate_more_questions(ctx: dict, quiz_id: int) -> str:
    """Tops up an existing quiz from its already-extracted source text. The
    route's atomic UPDATE already claimed `generating_more` before
    enqueueing this — this task's job is just to run the generation and
    always clear that flag when done, success or failure."""
    async with ctx["db_factory"]() as db:
        # source_text is deferred on the model (never loaded on ordinary
        # queries — it's the reason list/poll queries stay cheap); this is
        # the one place it's actually needed, so explicitly undefer it.
        quiz = await db.get(Quiz, quiz_id, options=[undefer(Quiz.source_text)])
        if quiz is None:
            return "quiz missing"

        try:
            new_questions = await quiz_engine.generate_more(
                quiz.source_text, quiz.questions or [], quiz.difficulty, quiz.language
            )
            # Reassignment, not .append() — questions is a plain JSONB
            # column (no MutableList wrapper), so an in-place mutation
            # wouldn't be detected as a change by SQLAlchemy.
            quiz.questions = (quiz.questions or []) + new_questions
            quiz.generate_more_error = None
        except Exception as exc:
            logger.exception("Generate-more failed for quiz %s", quiz_id)
            quiz.generate_more_error = f"{type(exc).__name__}: {exc}"[:500].strip(": ")
        finally:
            quiz.generating_more = False

        try:
            await db.commit()
        except Exception as exc:
            # Same rationale as generate_quiz's final-commit guard. This
            # one also has the 35-minute stuck-job fallback in the route's
            # atomic UPDATE guard as a second safety net, but there's no
            # reason to make the user wait that long when we can just fix
            # it immediately.
            logger.exception(
                "Quiz %s: generate-more commit failed — clearing "
                "generating_more instead of leaving it stuck", quiz_id,
            )
            await db.rollback()
            await db.execute(
                update(Quiz)
                .where(Quiz.id == quiz_id)
                .values(
                    generating_more=False,
                    generate_more_error=f"Save failed: {type(exc).__name__}: {exc}"[:500].strip(": "),
                )
            )
            await db.commit()
        return f"quiz {quiz_id}: generate-more done"
