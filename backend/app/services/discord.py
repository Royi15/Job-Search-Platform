"""Discord community channel broadcasting.

Every newly found student job is posted to a shared Discord channel via a
channel webhook — a plain HTTPS POST, so no gateway connection or bot process
has to stay alive. Personal, preference-filtered alerts still go to each
user's Telegram; the Discord channel is the public firehose everyone can watch.
"""
import logging

import httpx

from app.core.config import get_settings
from app.models import Job

logger = logging.getLogger(__name__)


def _job_embed(job: Job) -> dict:
    location = job.location or ("Remote" if job.is_remote else "N/A")
    if job.location and job.is_remote:
        location += " (Remote)"
    return {
        "title": job.title[:256],
        "url": job.url,
        "color": 0x2ECC71,
        "fields": [
            {"name": "Company", "value": (job.company or "Unknown")[:1024], "inline": True},
            {"name": "Location", "value": location[:1024], "inline": True},
            {"name": "Source", "value": job.source, "inline": True},
        ],
        "footer": {"text": "Job Search Platform — student jobs feed"},
    }


async def broadcast_job(job: Job) -> bool:
    """Post one job to the community channel. Returns True on success."""
    webhook_url = get_settings().discord_webhook_url
    if not webhook_url:
        logger.debug("DISCORD_WEBHOOK_URL not set — skipping broadcast")
        return False
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            webhook_url,
            json={"content": "🎓 **New student job found!**", "embeds": [_job_embed(job)]},
        )
    # Discord returns 204 on success; 429 means we're rate-limited (30 req/min
    # per webhook) — the job stays unmarked and is retried next cron cycle.
    if response.status_code not in (200, 204):
        logger.error("Discord webhook failed (%s): %s", response.status_code, response.text[:300])
        return False
    return True
