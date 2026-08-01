import uuid
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, UploadFile, status
from sqlalchemy import and_, func, or_, select, text, update

from app.api.deps import DB, CurrentUser, Queue
from app.core.config import get_settings
from app.models import Quiz
from app.schemas.quiz import QuizOut
from app.services.quiz import MAX_QUESTIONS_PER_QUIZ

router = APIRouter(prefix="/quizzes", tags=["quizzes"])

LANGUAGES = ("en", "he")
DIFFICULTIES = ("easy", "medium", "hard")
CONTENT_TYPE_MAP = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
}

# How long a "generating_more" job can run before the atomic guard below
# treats it as stuck (worker killed mid-run — this runs on a 1 GiB VM,
# OOM-kills are a real possibility) and allows a retry rather than wedging
# the quiz forever. A bit past the worker's own job_timeout (settings.py).
GENERATE_MORE_STUCK_AFTER = text("interval '35 minutes'")


async def _owned_quiz(db, user_id: int, quiz_id: int) -> Quiz:
    quiz = await db.scalar(select(Quiz).where(Quiz.id == quiz_id, Quiz.user_id == user_id))
    if quiz is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Quiz not found")
    return quiz


@router.post("", response_model=QuizOut, status_code=status.HTTP_202_ACCEPTED)
async def upload_quiz_source(
    file: UploadFile,
    user: CurrentUser,
    db: DB,
    queue: Queue,
    language: str = Form("en"),
    difficulty: str = Form("medium"),
):
    """Store the source file and enqueue quiz generation — returns before any heavy work."""
    settings = get_settings()
    if language not in LANGUAGES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unsupported language")
    if difficulty not in DIFFICULTIES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unsupported difficulty")
    source_type = CONTENT_TYPE_MAP.get(file.content_type or "")
    if source_type is None:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Supported formats: PDF, PPTX, MP3"
        )

    content = await file.read()
    # MP3 goes through the Files API (much higher ceiling); PDF/PPTX stay
    # inline, capped at Gemini's inline-request limit — same split notebook
    # sources use.
    max_bytes = (
        settings.max_notebook_audio_bytes
        if source_type == "mp3"
        else settings.max_notebook_upload_bytes
    )
    if len(content) > max_bytes:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"File exceeds {max_bytes // (1024 * 1024)} MB limit",
        )

    # Cap on how many quizzes a user can have AT ONCE, not a lifetime total
    # — deleting a quiz frees up a slot. (A prior version of this used a
    # monotonic, never-decreasing counter specifically so deleting couldn't
    # be used to generate unlimited quizzes over time; the user explicitly
    # chose to trade that cost guarantee for the friendlier "delete one to
    # make room" behavior instead.) Not fully race-proof under concurrent
    # uploads from the same user (two requests could both count 29 and both
    # proceed) — an acceptable, self-correcting gap for a soft UX cap, not
    # worth an advisory lock for.
    current_count = await db.scalar(
        select(func.count()).select_from(Quiz).where(Quiz.user_id == user.id)
    )
    if current_count >= settings.quiz_generation_limit:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"You've reached the limit of {settings.quiz_generation_limit} quizzes. "
            "Delete one to make room for a new one.",
        )

    user_dir = Path(settings.upload_dir) / str(user.id)
    user_dir.mkdir(parents=True, exist_ok=True)
    storage_path = user_dir / f"{uuid.uuid4()}.{source_type}"
    storage_path.write_bytes(content)

    original_filename = file.filename or f"quiz.{source_type}"
    quiz = Quiz(
        user_id=user.id,
        original_filename=original_filename,
        source_type=source_type,
        title=Path(original_filename).stem,
        language=language,
        difficulty=difficulty,
        storage_path=str(storage_path),
    )
    db.add(quiz)
    await db.commit()
    await db.refresh(quiz)

    await queue.enqueue_job("generate_quiz", quiz.id)
    return quiz


@router.post("/{quiz_id}/generate-more", response_model=QuizOut, status_code=status.HTTP_202_ACCEPTED)
async def generate_more_quiz_questions(quiz_id: int, user: CurrentUser, db: DB, queue: Queue):
    """Top up an existing quiz with more questions from the same source.
    Doesn't count against quiz_generation_limit — that's a cap on new
    uploads, this extends one that already exists."""
    quiz = await _owned_quiz(db, user.id, quiz_id)
    if not quiz.can_generate_more:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "This quiz was created before Generate More was added — "
            "re-upload the source to use this feature",
        )

    # Atomic UPDATE with a WHERE guard, not check-then-set: prevents a
    # double-click or two open tabs from firing two overlapping generation
    # jobs (which would each snapshot the same existing-questions list and
    # could both land near-duplicate batches, or blow past the 100 cap
    # together). The second clause lets a genuinely stuck job (see
    # GENERATE_MORE_STUCK_AFTER) be retried instead of wedging forever.
    claimed = await db.execute(
        update(Quiz)
        .where(
            Quiz.id == quiz_id,
            or_(
                and_(Quiz.generating_more.is_(False), Quiz.status == "done"),
                and_(
                    Quiz.generating_more.is_(True),
                    Quiz.generate_more_started_at < func.now() - GENERATE_MORE_STUCK_AFTER,
                ),
            ),
            func.jsonb_array_length(func.coalesce(Quiz.questions, text("'[]'::jsonb")))
            < MAX_QUESTIONS_PER_QUIZ,
        )
        .values(generating_more=True, generate_more_error=None, generate_more_started_at=func.now())
        .returning(Quiz.id)
    )
    if claimed.first() is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Can't generate more right now (already running, quiz not ready, "
            f"or already at the {MAX_QUESTIONS_PER_QUIZ}-question limit)",
        )
    await db.commit()
    await db.refresh(quiz)

    await queue.enqueue_job("generate_more_questions", quiz.id)
    return quiz


@router.get("", response_model=list[QuizOut])
async def list_quizzes(user: CurrentUser, db: DB):
    # The frontend treats this list's length as the user's current quiz
    # count (for showing "X / limit" and gating the upload form), so this
    # limit must never be lower than quiz_generation_limit — otherwise a
    # user actually at the cap would see a truncated, understated count.
    result = await db.scalars(
        select(Quiz)
        .where(Quiz.user_id == user.id)
        .order_by(Quiz.created_at.desc())
        .limit(get_settings().quiz_generation_limit)
    )
    return result.all()


@router.get("/{quiz_id}", response_model=QuizOut)
async def get_quiz(quiz_id: int, user: CurrentUser, db: DB):
    return await _owned_quiz(db, user.id, quiz_id)


@router.delete("/{quiz_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_quiz(quiz_id: int, user: CurrentUser, db: DB) -> None:
    quiz = await _owned_quiz(db, user.id, quiz_id)
    if quiz.storage_path:
        Path(quiz.storage_path).unlink(missing_ok=True)
    await db.delete(quiz)
    await db.commit()
