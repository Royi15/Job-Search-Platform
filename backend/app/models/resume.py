from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, ForeignKey, Identity, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Resume(Base):
    __tablename__ = "resumes"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    original_filename: Mapped[str] = mapped_column(Text)
    storage_path: Mapped[str] = mapped_column(Text)
    raw_text: Mapped[str | None] = mapped_column(Text)
    extracted: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    parse_status: Mapped[str] = mapped_column(Text, server_default=text("'pending'"))
    is_primary: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    uploaded_at: Mapped[datetime] = mapped_column(server_default=func.now())
