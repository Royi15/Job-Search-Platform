"""Manually deliver a user's pending Telegram alerts (admin tool).

Queues the same deliver_pending_alerts task that runs when a user links
Telegram — useful when a user's alerts predate their linking and you don't
want to ask them to relink.

Usage (from backend/):
    .venv/bin/python -m scripts.deliver_alerts user@example.com
"""
import asyncio
import sys

from arq import create_pool
from arq.connections import RedisSettings
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import SessionFactory
from app.models import User


async def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m scripts.deliver_alerts <user-email>")
    email = sys.argv[1]

    async with SessionFactory() as db:
        user = await db.scalar(select(User).where(User.email == email))
    if user is None:
        raise SystemExit(f"No user with email {email}")
    if user.telegram_chat_id is None:
        raise SystemExit(f"{email} has not linked Telegram — nowhere to deliver")

    redis = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    await redis.enqueue_job("deliver_pending_alerts", user.id)
    await redis.aclose()
    print(f"Queued pending-alert delivery for {email} (user id {user.id})")


asyncio.run(main())
