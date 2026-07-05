"""Bright Data LinkedIn jobs dataset — the student-jobs discovery source.

Uses the "discover by keyword" scrape API. Dedup strategy: LinkedIn's
job_posting_id is stored as jobs.external_id, and the UNIQUE(source,
external_id) constraint drops anything we've already seen — so users and the
Discord channel are never notified twice about the same posting, no matter
how often the scrape re-returns it.

The /scrape endpoint is synchronous when the crawl is fast; when it takes
longer Bright Data answers with a snapshot_id that we poll until ready.
"""
import asyncio
import logging
from datetime import datetime

import httpx

from app.core.config import get_settings
from app.services.job_sources.base import FetchedJob

logger = logging.getLogger(__name__)

SCRAPE_URL = "https://api.brightdata.com/datasets/v3/scrape"
SNAPSHOT_URL = "https://api.brightdata.com/datasets/v3/snapshot/{snapshot_id}"

POLL_INTERVAL_SECONDS = 15
POLL_BUDGET_SECONDS = 480  # stay under the worker's 600 s cron timeout


class BrightDataLinkedInSource:
    name = "linkedin"

    async def fetch_recent(self) -> list[FetchedJob]:
        settings = get_settings()
        headers = {"Authorization": f"Bearer {settings.brightdata_api_key}"}
        params = {
            "dataset_id": settings.brightdata_dataset_id,
            "notify": "false",
            "include_errors": "true",
            "type": "discover_new",
            "discover_by": "keyword",
        }
        payload = {
            "input": [
                {
                    "keyword": settings.brightdata_keyword,
                    "location": settings.brightdata_location,
                    "country": settings.brightdata_country,
                    "time_range": settings.brightdata_time_range,
                    "job_type": "",
                    "experience_level": "",
                    "remote": "",
                    "company": "",
                    "location_radius": "",
                }
            ]
        }

        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                SCRAPE_URL, params=params, headers=headers, json=payload
            )
            response.raise_for_status()
            data = response.json()

            if isinstance(data, dict) and "snapshot_id" in data:
                # Crawl still running — poll the snapshot until it's ready.
                records = await self._poll_snapshot(client, headers, data["snapshot_id"])
            elif isinstance(data, list):
                records = data
            else:
                logger.error("Bright Data: unexpected response shape: %s", str(data)[:300])
                records = []

        jobs = []
        for record in records:
            if not record.get("job_posting_id"):
                continue  # error rows (include_errors=true) have no posting id
            jobs.append(self._normalize(record))
        return jobs

    async def _poll_snapshot(
        self, client: httpx.AsyncClient, headers: dict, snapshot_id: str
    ) -> list[dict]:
        url = SNAPSHOT_URL.format(snapshot_id=snapshot_id)
        waited = 0
        while waited < POLL_BUDGET_SECONDS:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            waited += POLL_INTERVAL_SECONDS
            response = await client.get(url, params={"format": "json"}, headers=headers)
            if response.status_code == 200:
                data = response.json()
                return data if isinstance(data, list) else []
            if response.status_code != 202:  # 202 = still building
                response.raise_for_status()
        logger.warning(
            "Bright Data snapshot %s not ready after %ss — jobs will be picked "
            "up on the next cron run", snapshot_id, POLL_BUDGET_SECONDS,
        )
        return []

    def _normalize(self, record: dict) -> FetchedJob:
        posted_at = None
        raw_date = record.get("job_posted_date")
        if raw_date:
            try:
                posted_at = datetime.fromisoformat(str(raw_date).replace("Z", "+00:00"))
            except ValueError:
                pass
        location = record.get("job_location") or ""
        return FetchedJob(
            source=self.name,
            external_id=str(record["job_posting_id"]),
            title=record.get("job_title") or "Untitled",
            url=record.get("url") or record.get("apply_link") or "",
            company=record.get("company_name"),
            location=location or None,
            is_remote="remote" in location.lower(),
            description=(record.get("job_summary") or "")[:20000] or None,
            posted_at=posted_at,
        )
