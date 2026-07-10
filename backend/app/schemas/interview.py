from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class InterviewStartRequest(BaseModel):
    resume_id: int
    job_description: str = Field(min_length=50, max_length=20000)


class InterviewAnswerRequest(BaseModel):
    answer: str = Field(max_length=8000)


class InterviewSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_description: str
    title: str | None
    stage: str
    status: str
    transcript: list[dict[str, Any]]
    report: dict[str, Any] | None
    created_at: datetime
