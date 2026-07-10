"""Manually re-run matching for a search preference against recently fetched
jobs (admin tool). This is the same task that fires automatically when a
user creates or updates a preference — useful after fixing a preference by
hand (e.g. correcting a keyword typo) without needing the user to resave it
on the site. Free: it only re-checks jobs already in our database, no
Bright Data scrape involved.

Usage (from backend/):
    .venv/bin/python -m scripts.rematch_preference <preference-id>
"""
import asyncio
import sys

from arq import create_pool
from arq.connections import RedisSettings

from app.core.config import get_settings
from app.core.database import SessionFactory
from app.models import SearchPreference


async def main() -> None:
    if len(sys.argv) != 2 or not sys.argv[1].isdigit():
        raise SystemExit("usage: python -m scripts.rematch_preference <preference-id>")
    pref_id = int(sys.argv[1])

    async with SessionFactory() as db:
        pref = await db.get(SearchPreference, pref_id)
    if pref is None:
        raise SystemExit(f"No preference with id {pref_id}")
    if not pref.is_active:
        raise SystemExit(f"Preference {pref_id} ({pref.name!r}) is paused — activate it first")

    redis = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    await redis.enqueue_job("match_preference", pref.id)
    await redis.aclose()
    print(f"Queued re-match for preference {pref_id} ({pref.name!r})")


asyncio.run(main())
