import enum
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Enum, ForeignKey, Identity, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class GenerationKind(str, enum.Enum):
    RESUME_TAILORING = "resume_tailoring"
    COVER_LETTER = "cover_letter"
    LINKEDIN_MESSAGE = "linkedin_message"


class AIGeneration(Base):
    __tablename__ = "ai_generations"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    resume_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("resumes.id", ondelete="SET NULL")
    )
    application_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("applications.id", ondelete="SET NULL")
    )
    kind: Mapped[GenerationKind] = mapped_column(
        Enum(
            GenerationKind,
            name="generation_kind",
            create_type=False,
            values_callable=lambda e: [m.value for m in e],
        )
    )
    job_description: Mapped[str] = mapped_column(Text)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(Text, server_default=text("'pending'"))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    completed_at: Mapped[datetime | None]
