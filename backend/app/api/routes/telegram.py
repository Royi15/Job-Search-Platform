"""Telegram integration: the link endpoint the web app uses, and the webhook
Telegram calls when a user sends the bot /start <token>."""
import logging
import uuid

from fastapi import APIRouter, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DB, CurrentUser
from app.core.config import get_settings
from app.models import User
from app.services import telegram as tg

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/telegram", tags=["telegram"])


@router.get("/link")
async def link_info(user: CurrentUser):
    """The web UI shows this deep link; tapping it links the Telegram account."""
    return {
        "linked": user.telegram_chat_id is not None,
        "deep_link": tg.deep_link(user.telegram_link_token),
    }


@router.post("/unlink", status_code=status.HTTP_204_NO_CONTENT)
async def unlink(user: CurrentUser, db: DB) -> None:
    user.telegram_chat_id = None
    user.telegram_link_token = uuid.uuid4()  # old deep link stops working
    db.add(user)
    await db.commit()


async def _handle_start(db: AsyncSession, chat_id: int, payload: str) -> None:
    try:
        token = uuid.UUID(payload)
    except ValueError:
        await tg.send_message(chat_id, "Invalid link. Get a fresh one from the web app.")
        return

    user = await db.scalar(select(User).where(User.telegram_link_token == token))
    if user is None:
        await tg.send_message(chat_id, "Link expired. Get a fresh one from the web app.")
        return

    user.telegram_chat_id = chat_id
    await db.commit()
    await tg.send_message(
        chat_id, "✅ Linked! You'll get a message here whenever a matching job is found."
    )


@router.post("/webhook", include_in_schema=False)
async def webhook(
    request: Request,
    db: DB,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
):
    settings = get_settings()
    if (
        not settings.telegram_webhook_secret
        or x_telegram_bot_api_secret_token != settings.telegram_webhook_secret
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bad webhook secret")

    update = await request.json()
    message = update.get("message") or {}
    text = message.get("text", "")
    chat_id = (message.get("chat") or {}).get("id")

    if chat_id and text.startswith("/start"):
        parts = text.split(maxsplit=1)
        if len(parts) == 2:
            await _handle_start(db, chat_id, parts[1].strip())
        else:
            await tg.send_message(
                chat_id, "Hi! Link your account from the web app to get job alerts."
            )
    # Always 200 — otherwise Telegram retries the same update forever.
    return {"ok": True}
