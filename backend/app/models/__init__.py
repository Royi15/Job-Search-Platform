"""ORM models — a 1:1 mirror of db/schema.sql (which owns the schema)."""
from app.models.user import User
from app.models.preference import SearchPreference
from app.models.job import Job, JobAlert
from app.models.application import Application, ApplicationEvent, ApplicationStatus
from app.models.resume import Resume
from app.models.generation import AIGeneration, GenerationKind

__all__ = [
    "User",
    "SearchPreference",
    "Job",
    "JobAlert",
    "Application",
    "ApplicationEvent",
    "ApplicationStatus",
    "Resume",
    "AIGeneration",
    "GenerationKind",
]
