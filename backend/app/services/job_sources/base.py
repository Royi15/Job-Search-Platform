from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class FetchedJob:
    """Normalized posting — the only shape the rest of the system knows."""

    source: str
    external_id: str
    title: str
    url: str
    company: str | None = None
    location: str | None = None
    is_remote: bool = False
    description: str | None = None
    posted_at: datetime | None = None


class JobSource(Protocol):
    """One adapter per external job board / API."""

    name: str

    async def fetch_recent(self) -> list[FetchedJob]:
        """Return recent postings. Errors should raise; the worker logs and
        continues with the other sources."""
        ...
