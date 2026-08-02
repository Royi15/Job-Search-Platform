from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, ForeignKey, Identity, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, column_property, mapped_column

from app.core.database import Base


class Quiz(Base):
    __tablename__ = "quizzes"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    original_filename: Mapped[str] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(Text, server_default=text("'pdf'"))
    storage_path: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str] = mapped_column(Text, server_default=text("'en'"))
    difficulty: Mapped[str] = mapped_column(Text, server_default=text("'medium'"))
    questions: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(Text, server_default=text("'pending'"))
    error: Mapped[str | None] = mapped_column(Text)
    # Extracted PDF text, kept (unlike the source file, which stays
    # single-use and deleted) so "generate more" can regenerate against the
    # same source without re-uploading. Deferred — list/poll queries hit
    # this table every 3s while anything is in flight, and this column can
    # be up to ~900KB; loading it on every poll would be wasteful. Only the
    # generate-more worker task explicitly undefers it.
    source_text: Mapped[str | None] = mapped_column(Text, deferred=True)
    # A SQL-level boolean (not a Python property reading source_text) so
    # the frontend can tell whether "generate more" is available without
    # ever loading the deferred column itself — reading a deferred
    # attribute from Pydantic's sync serialization would trigger an
    # implicit lazy-load that raises under async SQLAlchemy.
    can_generate_more: Mapped[bool] = column_property(source_text.isnot(None))
    generating_more: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    generate_more_error: Mapped[str | None] = mapped_column(Text)
    # Lets a stuck job (worker killed mid-run) self-heal instead of
    # wedging the quiz in "generating_more" forever — see routes/quizzes.py.
    generate_more_started_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    completed_at: Mapped[datetime | None]
