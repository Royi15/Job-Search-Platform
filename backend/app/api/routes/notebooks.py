import uuid
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, UploadFile, status
from sqlalchemy import func, select

from app.api.deps import DB, CurrentUser, Queue
from app.core.config import get_settings
from app.models import Notebook
from app.schemas.notebook import NotebookOut

router = APIRouter(prefix="/notebooks", tags=["notebooks"])

CONTENT_TYPE_MAP = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
}
LANGUAGES = ("en", "he")


async def _owned_notebook(db, user_id: int, notebook_id: int) -> Notebook:
    notebook = await db.scalar(
        select(Notebook).where(Notebook.id == notebook_id, Notebook.user_id == user_id)
    )
    if notebook is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notebook not found")
    return notebook


@router.post("", response_model=NotebookOut, status_code=status.HTTP_202_ACCEPTED)
async def upload_notebook_source(
    file: UploadFile, user: CurrentUser, db: DB, queue: Queue, language: str = Form("en")
):
    """Store the source file and enqueue generation — returns before any heavy work."""
    settings = get_settings()
    if language not in LANGUAGES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unsupported language")
    source_type = CONTENT_TYPE_MAP.get(file.content_type or "")
    if source_type is None:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Supported formats: PDF, PPTX, MP3"
        )

    content = await file.read()
    # MP3 goes through the Files API (much higher ceiling); PDF/PPTX stay
    # inline, capped at Gemini's inline-request limit.
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

    # Cap on how many notebooks a user can have AT ONCE, not a lifetime
    # total — deleting one frees up a slot. Same reasoning and pattern as
    # quizzes' cap (routes/quizzes.py): not race-proof under concurrent
    # uploads from the same user, an acceptable, self-correcting gap for a
    # soft UX cap.
    current_count = await db.scalar(
        select(func.count()).select_from(Notebook).where(Notebook.user_id == user.id)
    )
    if current_count >= settings.notebook_generation_limit:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"You've reached the limit of {settings.notebook_generation_limit} notebooks. "
            "Delete one to make room for a new one.",
        )

    user_dir = Path(settings.upload_dir) / str(user.id)
    user_dir.mkdir(parents=True, exist_ok=True)
    storage_path = user_dir / f"{uuid.uuid4()}.{source_type}"
    storage_path.write_bytes(content)

    notebook = Notebook(
        user_id=user.id,
        original_filename=file.filename or f"notebook.{source_type}",
        source_type=source_type,
        language=language,
        storage_path=str(storage_path),
    )
    db.add(notebook)
    await db.commit()
    await db.refresh(notebook)

    await queue.enqueue_job("generate_notebook", notebook.id)
    return notebook


@router.get("", response_model=list[NotebookOut])
async def list_notebooks(user: CurrentUser, db: DB):
    # The frontend treats this list's length as the user's current notebook
    # count (for showing "X / limit" and gating the upload form), so this
    # limit must never be lower than notebook_generation_limit — otherwise
    # a user actually at the cap would see a truncated, understated count.
    result = await db.scalars(
        select(Notebook)
        .where(Notebook.user_id == user.id)
        .order_by(Notebook.created_at.desc())
        .limit(get_settings().notebook_generation_limit)
    )
    return result.all()


@router.get("/{notebook_id}", response_model=NotebookOut)
async def get_notebook(notebook_id: int, user: CurrentUser, db: DB):
    return await _owned_notebook(db, user.id, notebook_id)


@router.delete("/{notebook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_notebook(notebook_id: int, user: CurrentUser, db: DB) -> None:
    notebook = await _owned_notebook(db, user.id, notebook_id)
    if notebook.storage_path:
        Path(notebook.storage_path).unlink(missing_ok=True)
    await db.delete(notebook)
    await db.commit()
