from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Identity,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (UniqueConstraint("source", "external_id"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    source: Mapped[str] = mapped_column(Text)
    external_id: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    company: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(Text)
    is_remote: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    url: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    posted_at: Mapped[datetime | None]
    first_seen_at: Mapped[datetime] = mapped_column(server_default=func.now())
    discord_notified_at: Mapped[datetime | None]


class JobAlert(Base):
    __tablename__ = "job_alerts"
    __table_args__ = (UniqueConstraint("user_id", "job_id"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    job_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("jobs.id", ondelete="CASCADE")
    )
    preference_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("search_preferences.id", ondelete="SET NULL")
    )
    matched_at: Mapped[datetime] = mapped_column(server_default=func.now())
    notified_at: Mapped[datetime | None]
    dismissed: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))

    job: Mapped[Job] = relationship(lazy="joined")
