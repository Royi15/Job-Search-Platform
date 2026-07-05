from datetime import datetime

from pydantic import BaseModel, ConfigDict


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    title: str
    company: str | None
    location: str | None
    is_remote: bool
    url: str
    description: str | None
    posted_at: datetime | None


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    matched_at: datetime
    notified_at: datetime | None
    dismissed: bool
    job: JobOut
