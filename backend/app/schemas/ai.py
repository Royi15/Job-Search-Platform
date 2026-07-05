from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.generation import GenerationKind


class TailorRequest(BaseModel):
    resume_id: int
    job_description: str = Field(min_length=50, max_length=20000)
    application_id: int | None = None


class CoverLetterRequest(BaseModel):
    resume_id: int
    job_description: str = Field(min_length=50, max_length=20000)
    kind: GenerationKind = GenerationKind.COVER_LETTER
    application_id: int | None = None


class GenerationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: GenerationKind
    status: str
    result: dict[str, Any] | None
    error: str | None
    created_at: datetime
    completed_at: datetime | None
