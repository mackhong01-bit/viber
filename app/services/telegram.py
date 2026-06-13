"""Lightweight Telegram sender. Skips silently if not configured."""
import asyncio
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


def _api(method: str) -> str:
    return f"https://api.telegram.org/bot{settings.telegram_bot_token}/{method}"


async def send_message(chat_id: str, text: str, parse_mode: str = "HTML") -> bool:
    if not settings.telegram_bot_token or not chat_id:
        logger.debug("Telegram not configured; skipping send.")
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                _api("sendMessage"),
                json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode},
            )
            if r.status_code != 200:
                logger.warning("Telegram send failed: %s %s", r.status_code, r.text)
                return False
            return True
    except Exception as e:
        logger.exception("Telegram send error: %s", e)
        return False


def send_sync(chat_id: str, text: str) -> bool:
    try:
        return asyncio.run(send_message(chat_id, text))
    except RuntimeError:
        # already in event loop
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(send_message(chat_id, text))
