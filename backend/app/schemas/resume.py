from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ResumeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    original_filename: str
    parse_status: str
    extracted: dict[str, Any] | None
    is_primary: bool
    uploaded_at: datetime
