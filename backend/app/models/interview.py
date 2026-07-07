from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Identity, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class InterviewSession(Base):
    __tablename__ = "interview_sessions"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    resume_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("resumes.id", ondelete="SET NULL")
    )
    job_description: Mapped[str] = mapped_column(Text)
    stage: Mapped[str] = mapped_column(Text, server_default=text("'behavioral'"))
    status: Mapped[str] = mapped_column(Text, server_default=text("'active'"))
    transcript: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, server_default=text("'[]'")
    )
    report: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    completed_at: Mapped[datetime | None]
