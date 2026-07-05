"""Remotive — free public API, no key needed. https://remotive.com/api

Serves as the reference adapter; copy this file to integrate any other board.
"""
import re
from datetime import datetime

import httpx

from app.services.job_sources.base import FetchedJob

API_URL = "https://remotive.com/api/remote-jobs"
TAG_RE = re.compile(r"<[^>]+>")


class RemotiveSource:
    name = "remotive"

    def __init__(self, categories: tuple[str, ...] = ("software-dev",), limit: int = 50):
        self._categories = categories
        self._limit = limit

    async def fetch_recent(self) -> list[FetchedJob]:
        jobs: list[FetchedJob] = []
        async with httpx.AsyncClient(timeout=30) as client:
            for category in self._categories:
                response = await client.get(
                    API_URL, params={"category": category, "limit": self._limit}
                )
                response.raise_for_status()
                for item in response.json().get("jobs", []):
                    jobs.append(self._normalize(item))
        return jobs

    def _normalize(self, item: dict) -> FetchedJob:
        posted_at = None
        if item.get("publication_date"):
            try:
                posted_at = datetime.fromisoformat(item["publication_date"])
            except ValueError:
                pass
        return FetchedJob(
            source=self.name,
            external_id=str(item["id"]),
            title=item.get("title", "Untitled"),
            url=item.get("url", ""),
            company=item.get("company_name"),
            location=item.get("candidate_required_location"),
            is_remote=True,  # Remotive lists remote jobs only
            description=TAG_RE.sub(" ", item.get("description", ""))[:20000],
            posted_at=posted_at,
        )
