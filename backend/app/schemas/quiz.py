from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class QuizOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    original_filename: str
    source_type: str
    title: str | None
    language: str
    difficulty: str
    questions: list[dict[str, Any]] | None
    status: str
    error: str | None
    can_generate_more: bool
    generating_more: bool
    generate_more_error: str | None
    created_at: datetime
    completed_at: datetime | None
