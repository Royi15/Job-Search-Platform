from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.application import ApplicationStatus


class ApplicationCreate(BaseModel):
    company: str = Field(min_length=1)
    title: str = Field(min_length=1)
    url: str | None = None
    status: ApplicationStatus = ApplicationStatus.APPLIED
    notes: str | None = None
    applied_at: date | None = None


class ApplicationUpdate(BaseModel):
    company: str | None = None
    title: str | None = None
    url: str | None = None
    notes: str | None = None
    applied_at: date | None = None


class ApplicationMove(BaseModel):
    """Drag & drop: new column and/or new position within a column."""

    status: ApplicationStatus
    sort_order: float


class ApplicationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: int | None
    company: str
    title: str
    url: str | None
    status: ApplicationStatus
    sort_order: float
    notes: str | None
    applied_at: date
    updated_at: datetime


class ApplicationEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    from_status: ApplicationStatus | None
    to_status: ApplicationStatus
    changed_at: datetime
