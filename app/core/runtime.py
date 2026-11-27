"""Shared references to running services (set in run.py) to avoid circular imports."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Awaitable, Callable

if TYPE_CHECKING:
    from app.admin.bot import AdminBot
    from app.channels.instagram import InstagramChannel
    from app.channels.telegram_userbot import UserBot
    from app.channels.youtube import YouTubeChannel
    from app.core.llm import LLM

llm: "LLM | None" = None
userbot: "UserBot | None" = None
admin_bot: "AdminBot | None" = None
youtube: "YouTubeChannel | None" = None
instagram: "InstagramChannel | None" = None

# Simple in-process pub/sub (admin bot subscribes to notifications)
_subscribers: dict[str, list[Callable[[Any], Awaitable[None]]]] = {}


def subscribe(event_name: str, handler: Callable[[Any], Awaitable[None]]) -> None:
    _subscribers.setdefault(event_name, []).append(handler)


async def publish(event_name: str, data: Any) -> None:
    import logging

    for handler in _subscribers.get(event_name, []):
        try:
            await handler(data)
        except Exception:
            logging.getLogger("agent").exception("event handler failed: %s", event_name)


def require_llm() -> "LLM":
    if llm is None:
        raise RuntimeError("Gemini sozlanmagan: .env faylida GEMINI_API_KEY ni kiriting")
    return llm
