import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, status
from sqlalchemy import select, update

from app.api.deps import DB, CurrentUser, Queue
from app.core.config import get_settings
from app.models import Resume
from app.schemas.resume import ResumeOut

router = APIRouter(prefix="/resumes", tags=["resumes"])


@router.post("", response_model=ResumeOut, status_code=status.HTTP_202_ACCEPTED)
async def upload_resume(file: UploadFile, user: CurrentUser, db: DB, queue: Queue):
    """Store the PDF and enqueue parsing — returns before any heavy work."""
    settings = get_settings()
    if file.content_type != "application/pdf":
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "PDF files only")

    content = await file.read()
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"File exceeds {settings.max_upload_bytes // (1024 * 1024)} MB limit",
        )

    user_dir = Path(settings.upload_dir) / str(user.id)
    user_dir.mkdir(parents=True, exist_ok=True)
    storage_path = user_dir / f"{uuid.uuid4()}.pdf"
    storage_path.write_bytes(content)

    resume = Resume(
        user_id=user.id,
        original_filename=file.filename or "resume.pdf",
        storage_path=str(storage_path),
    )
    db.add(resume)
    await db.commit()
    await db.refresh(resume)

    await queue.enqueue_job("parse_resume", resume.id)
    return resume


@router.get("", response_model=list[ResumeOut])
async def list_resumes(user: CurrentUser, db: DB):
    result = await db.scalars(
        select(Resume)
        .where(Resume.user_id == user.id)
        .order_by(Resume.uploaded_at.desc())
    )
    return result.all()


@router.get("/{resume_id}", response_model=ResumeOut)
async def get_resume(resume_id: int, user: CurrentUser, db: DB):
    resume = await db.scalar(
        select(Resume).where(Resume.id == resume_id, Resume.user_id == user.id)
    )
    if resume is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Resume not found")
    return resume


@router.post("/{resume_id}/primary", response_model=ResumeOut)
async def set_primary(resume_id: int, user: CurrentUser, db: DB):
    resume = await db.scalar(
        select(Resume).where(Resume.id == resume_id, Resume.user_id == user.id)
    )
    if resume is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Resume not found")
    # Clear the old primary first — a partial unique index enforces one per user.
    await db.execute(
        update(Resume)
        .where(Resume.user_id == user.id, Resume.is_primary.is_(True))
        .values(is_primary=False)
    )
    resume.is_primary = True
    await db.commit()
    await db.refresh(resume)
    return resume
