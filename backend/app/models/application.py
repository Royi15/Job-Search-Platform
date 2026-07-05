import enum
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Date,
    Double,
    Enum,
    ForeignKey,
    Identity,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ApplicationStatus(str, enum.Enum):
    APPLIED = "applied"
    PHONE_INTERVIEW = "phone_interview"
    HOME_ASSIGNMENT = "home_assignment"
    TECHNICAL_INTERVIEW = "technical_interview"
    REJECTED = "rejected"
    OFFER = "offer"


# The PG enum type is created by db/schema.sql, never by the ORM.
status_enum = Enum(
    ApplicationStatus,
    name="application_status",
    create_type=False,
    values_callable=lambda e: [m.value for m in e],
)


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    job_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("jobs.id", ondelete="SET NULL")
    )
    company: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ApplicationStatus] = mapped_column(
        status_enum, server_default=text("'applied'")
    )
    sort_order: Mapped[float] = mapped_column(Double, server_default=text("0"))
    notes: Mapped[str | None] = mapped_column(Text)
    applied_at: Mapped[date] = mapped_column(Date, server_default=func.current_date())
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ApplicationEvent(Base):
    __tablename__ = "application_events"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    application_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    from_status: Mapped[ApplicationStatus | None] = mapped_column(status_enum)
    to_status: Mapped[ApplicationStatus] = mapped_column(status_enum)
    changed_at: Mapped[datetime] = mapped_column(server_default=func.now())
