from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PreferenceBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    title_keywords: list[str] = Field(min_length=1)
    must_have_keywords: list[str] = []
    exclude_keywords: list[str] = []
    locations: list[str] = []
    remote_ok: bool = True
    is_active: bool = True


class PreferenceCreate(PreferenceBase):
    pass


class PreferenceUpdate(BaseModel):
    name: str | None = None
    title_keywords: list[str] | None = None
    must_have_keywords: list[str] | None = None
    exclude_keywords: list[str] | None = None
    locations: list[str] | None = None
    remote_ok: bool | None = None
    is_active: bool | None = None


class PreferenceOut(PreferenceBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
