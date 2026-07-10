"""Simulated interview: the API drives the stage machine and generates the
next question synchronously (short LLM calls, a few seconds); final grading
runs in the worker because it's a heavyweight call the user polls for."""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import DB, CurrentUser, Queue
from app.models import InterviewSession, Resume
from app.schemas.interview import (
    InterviewAnswerRequest,
    InterviewSessionOut,
    InterviewStartRequest,
)
from app.services import interview as engine

router = APIRouter(prefix="/interviews", tags=["interview"])


async def _owned_session(db, user_id: int, session_id: int) -> InterviewSession:
    session = await db.scalar(
        select(InterviewSession).where(
            InterviewSession.id == session_id, InterviewSession.user_id == user_id
        )
    )
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Interview not found")
    return session


async def _resume_text(db, session: InterviewSession) -> str:
    if session.resume_id:
        resume = await db.get(Resume, session.resume_id)
        if resume and resume.raw_text:
            return resume.raw_text
    return "(resume unavailable)"


async def _excluded_questions(
    db, user_id: int, resume_id: int | None, exclude_session_id: int
) -> list[str]:
    """Questions already asked in this user's OTHER interviews with the same
    resume, so a repeat practice run gets fresh questions instead of the same
    ones the resume naturally draws out every time."""
    if resume_id is None:
        return []
    transcripts = (
        await db.scalars(
            select(InterviewSession.transcript).where(
                InterviewSession.user_id == user_id,
                InterviewSession.resume_id == resume_id,
                InterviewSession.id != exclude_session_id,
            )
        )
    ).all()
    questions = [e["question"] for t in transcripts for e in t if e.get("question")]
    return questions[-40:]  # cap so the prompt never grows unbounded


async def _title_for(db, job_description: str) -> str:
    """Same JD text always gets the same title: reuse a past title for this
    exact JD (ignoring whitespace differences) instead of asking the LLM
    again, which could phrase it slightly differently each time."""
    normalized = " ".join(job_description.split())
    rows = (
        await db.execute(
            select(InterviewSession.job_description, InterviewSession.title).where(
                InterviewSession.title.is_not(None)
            )
        )
    ).all()
    for jd, title in rows:
        if " ".join(jd.split()) == normalized:
            return title
    return await engine.generate_title(job_description)


@router.post("", response_model=InterviewSessionOut, status_code=status.HTTP_201_CREATED)
async def start_interview(body: InterviewStartRequest, user: CurrentUser, db: DB):
    resume = await db.scalar(
        select(Resume).where(Resume.id == body.resume_id, Resume.user_id == user.id)
    )
    if resume is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Resume not found")
    if resume.parse_status != "done" or not resume.raw_text:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Resume is still being parsed — try again shortly"
        )

    title = await _title_for(db, body.job_description)
    session = InterviewSession(
        user_id=user.id,
        resume_id=resume.id,
        job_description=body.job_description,
        title=title,
        transcript=[engine.new_entry("behavioral", engine.FIRST_QUESTION)],
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


@router.get("", response_model=list[InterviewSessionOut])
async def list_interviews(user: CurrentUser, db: DB):
    result = await db.scalars(
        select(InterviewSession)
        .where(InterviewSession.user_id == user.id)
        .order_by(InterviewSession.created_at.desc())
        .limit(30)
    )
    return result.all()


@router.get("/current", response_model=InterviewSessionOut)
async def current_interview(user: CurrentUser, db: DB):
    """Latest session — lets a page refresh resume an interview in progress."""
    session = await db.scalar(
        select(InterviewSession)
        .where(InterviewSession.user_id == user.id)
        .order_by(InterviewSession.created_at.desc())
        .limit(1)
    )
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No interviews yet")
    return session


@router.get("/{session_id}", response_model=InterviewSessionOut)
async def get_interview(session_id: int, user: CurrentUser, db: DB):
    return await _owned_session(db, user.id, session_id)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_interview(session_id: int, user: CurrentUser, db: DB) -> None:
    session = await _owned_session(db, user.id, session_id)
    await db.delete(session)
    await db.commit()


@router.post("/{session_id}/abandon", response_model=InterviewSessionOut)
async def abandon_interview(session_id: int, user: CurrentUser, db: DB):
    """User-initiated stop. Idempotent: calling it on an already-finished
    session is a no-op, so the frontend doesn't need to special-case errors.
    If grading was already queued, that task checks status=='grading' before
    running and will quietly skip once this flips it to 'abandoned'."""
    session = await _owned_session(db, user.id, session_id)
    if session.status in ("active", "grading"):
        session.status = "abandoned"
        session.completed_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(session)
    return session


@router.post("/{session_id}/answer", response_model=InterviewSessionOut)
async def answer_question(
    session_id: int, body: InterviewAnswerRequest, user: CurrentUser, db: DB, queue: Queue
):
    session = await _owned_session(db, user.id, session_id)
    if session.status != "active":
        raise HTTPException(status.HTTP_409_CONFLICT, "This interview is finished")

    transcript = [dict(entry) for entry in session.transcript]
    if not transcript or transcript[-1].get("answer") is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "No open question to answer")

    # Record the answer + server-side timing (the client timer is cosmetic)
    now = datetime.now(timezone.utc)
    current = transcript[-1]
    current["answer"] = body.answer.strip() or "(no answer)"
    current["answered_at"] = now.isoformat()
    if current.get("time_limit_seconds"):
        elapsed = (now - datetime.fromisoformat(current["asked_at"])).total_seconds()
        current["overtime"] = (
            elapsed > current["time_limit_seconds"] + engine.OVERTIME_GRACE_SECONDS
        )

    behavioral_done = sum(1 for e in transcript if e["stage"] == "behavioral")
    technical_done = sum(1 for e in transcript if e["stage"] == "technical")
    resume_text = await _resume_text(db, session)
    excluded = await _excluded_questions(db, user.id, session.resume_id, session.id)

    if session.stage == "behavioral":
        if behavioral_done < engine.BEHAVIORAL_QUESTIONS:
            question = await engine.next_behavioral_question(
                resume_text, session.job_description, transcript, excluded
            )
            transition = engine.pick_regular_transition(transcript)
            transcript.append(engine.new_entry("behavioral", question, transition=transition))
        else:
            session.stage = "technical"
            question = await engine.next_technical_question(
                resume_text, session.job_description, transcript, excluded
            )
            transition = engine.pick_stage_transition(transcript)
            transcript.append(
                engine.new_entry(
                    "technical",
                    question,
                    engine.TECHNICAL_TIME_LIMIT_SECONDS,
                    transition=transition,
                )
            )
    elif session.stage == "technical":
        if technical_done < engine.TECHNICAL_QUESTIONS:
            question = await engine.next_technical_question(
                resume_text, session.job_description, transcript, excluded
            )
            transition = engine.pick_regular_transition(transcript)
            transcript.append(
                engine.new_entry(
                    "technical",
                    question,
                    engine.TECHNICAL_TIME_LIMIT_SECONDS,
                    transition=transition,
                )
            )
        else:
            session.stage = "grading"
            session.status = "grading"

    session.transcript = transcript
    await db.commit()
    await db.refresh(session)

    if session.status == "grading":
        await queue.enqueue_job("grade_interview", session.id)
    return session
