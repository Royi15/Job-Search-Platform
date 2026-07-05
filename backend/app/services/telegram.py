"""Telegram bot helpers: outbound messages and account-link deep links.

Outbound only — inbound updates arrive via the webhook route
(api/routes/telegram.py), so no polling process is needed.
"""
import html
import logging
import uuid

import httpx

from app.core.config import get_settings
from app.models import Job

logger = logging.getLogger(__name__)

API_BASE = "https://api.telegram.org"


def deep_link(link_token: uuid.UUID) -> str:
    """t.me link the web app shows; tapping it sends /start <token> to the bot."""
    username = get_settings().telegram_bot_username
    return f"https://t.me/{username}?start={link_token}"


async def send_message(chat_id: int, text: str) -> bool:
    settings = get_settings()
    if not settings.telegram_bot_token:
        logger.warning("TELEGRAM_BOT_TOKEN not set — skipping message")
        return False
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            f"{API_BASE}/bot{settings.telegram_bot_token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": False,
            },
        )
    if response.status_code != 200:
        logger.error("Telegram sendMessage failed: %s", response.text[:300])
        return False
    return True


def format_job_alert(job: Job) -> str:
    parts = [
        "🎯 <b>New job match!</b>",
        f"<b>{html.escape(job.title)}</b>",
        html.escape(job.company or "Unknown company"),
    ]
    if job.location:
        parts.append(f"📍 {html.escape(job.location)}" + (" (Remote)" if job.is_remote else ""))
    elif job.is_remote:
        parts.append("📍 Remote")
    parts.append(f'<a href="{html.escape(job.url)}">View & apply →</a>')
    return "\n".join(parts)
