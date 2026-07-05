from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import DB, CurrentUser, Queue
from app.models import AIGeneration, GenerationKind, Resume
from app.schemas.ai import CoverLetterRequest, GenerationOut, TailorRequest

router = APIRouter(prefix="/ai", tags=["ai"])


async def _parsed_resume(db, user_id: int, resume_id: int) -> Resume:
    resume = await db.scalar(
        select(Resume).where(Resume.id == resume_id, Resume.user_id == user_id)
    )
    if resume is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Resume not found")
    if resume.parse_status != "done" or not resume.raw_text:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Resume is still being parsed — try again in a few seconds",
        )
    return resume


async def _enqueue_generation(
    db, queue, *, user_id: int, resume_id: int, kind: GenerationKind,
    job_description: str, application_id: int | None,
) -> AIGeneration:
    generation = AIGeneration(
        user_id=user_id,
        resume_id=resume_id,
        application_id=application_id,
        kind=kind,
        job_description=job_description,
    )
    db.add(generation)
    await db.commit()
    await db.refresh(generation)
    await queue.enqueue_job("run_generation", generation.id)
    return generation


@router.post("/tailor", response_model=GenerationOut, status_code=status.HTTP_202_ACCEPTED)
async def tailor_resume(body: TailorRequest, user: CurrentUser, db: DB, queue: Queue):
    """ATS gap analysis + sentence rewrites. Async: poll GET /ai/generations/{id}."""
    resume = await _parsed_resume(db, user.id, body.resume_id)
    return await _enqueue_generation(
        db, queue,
        user_id=user.id, resume_id=resume.id, kind=GenerationKind.RESUME_TAILORING,
        job_description=body.job_description, application_id=body.application_id,
    )


@router.post("/cover-letter", response_model=GenerationOut, status_code=status.HTTP_202_ACCEPTED)
async def cover_letter(body: CoverLetterRequest, user: CurrentUser, db: DB, queue: Queue):
    if body.kind == GenerationKind.RESUME_TAILORING:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Use /ai/tailor for tailoring")
    resume = await _parsed_resume(db, user.id, body.resume_id)
    return await _enqueue_generation(
        db, queue,
        user_id=user.id, resume_id=resume.id, kind=body.kind,
        job_description=body.job_description, application_id=body.application_id,
    )


@router.get("/generations", response_model=list[GenerationOut])
async def list_generations(user: CurrentUser, db: DB):
    result = await db.scalars(
        select(AIGeneration)
        .where(AIGeneration.user_id == user.id)
        .order_by(AIGeneration.created_at.desc())
        .limit(50)
    )
    return result.all()


@router.get("/generations/{generation_id}", response_model=GenerationOut)
async def get_generation(generation_id: int, user: CurrentUser, db: DB):
    generation = await db.scalar(
        select(AIGeneration).where(
            AIGeneration.id == generation_id, AIGeneration.user_id == user.id
        )
    )
    if generation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Generation not found")
    return generation
