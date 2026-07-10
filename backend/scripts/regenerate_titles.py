"""Regenerate all interview titles (admin tool) — run once after changing
the title prompt/format, so existing interviews pick up the new format
instead of keeping whatever an older prompt produced. Identical job
descriptions are only sent to Gemini once per run (cached locally), so a
handful of unique JDs shared across many interviews costs one call each.

Usage (from backend/):
    .venv/bin/python -m scripts.regenerate_titles
"""
import asyncio

from sqlalchemy import select

from app.core.database import SessionFactory
from app.models import InterviewSession
from app.services.interview import generate_title


async def main() -> None:
    async with SessionFactory() as db:
        sessions = (await db.scalars(select(InterviewSession))).all()
        cache: dict[str, str] = {}
        updated = 0
        for session in sessions:
            key = " ".join(session.job_description.split())
            if key not in cache:
                cache[key] = await generate_title(session.job_description)
                print(f"Generated: {cache[key]!r}")
            if session.title != cache[key]:
                session.title = cache[key]
                updated += 1
        await db.commit()
        print(f"Updated {updated}/{len(sessions)} interviews, {len(cache)} unique job descriptions")


asyncio.run(main())
