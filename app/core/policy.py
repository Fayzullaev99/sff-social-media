"""Hard safety rules: whitelist, rate limits, working hours and the money guard."""
from __future__ import annotations

import time
from collections import deque
from datetime import datetime

from app.core.state import get_settings

# Approval kinds that spend money. These can NEVER be executed without an explicit human approval.
MONEY_KINDS: frozenset[str] = frozenset(
    {
        "ad_campaign_launch",
        "ad_budget_change",
        "ad_campaign_resume",
        "paid_promotion",
        "paid_service",
    }
)


class MoneyActionBlocked(PermissionError):
    """Raised when something tries to run a money-spending action without human approval."""


def is_money_kind(kind: str) -> bool:
    return kind in MONEY_KINDS


class RateLimiter:
    """Global per-minute cap + per-chat cooldown to keep the Telegram account safe."""

    def __init__(self):
        self._global: deque[float] = deque()
        self._per_chat: dict[int, float] = {}

    def allow(self, chat_id: int, *, now: float | None = None) -> bool:
        b = get_settings().get("behavior", {})
        max_per_min = int(b.get("max_replies_per_minute", 20))
        cooldown = float(b.get("per_chat_cooldown_sec", 3))
        now = time.monotonic() if now is None else now
        while self._global and now - self._global[0] > 60:
            self._global.popleft()
        if len(self._global) >= max_per_min:
            return False
        if now - self._per_chat.get(chat_id, -1e9) < cooldown:
            return False
        return True

    def record(self, chat_id: int, *, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        self._global.append(now)
        self._per_chat[chat_id] = now


def within_working_hours(now: datetime | None = None, spec: str | None = None) -> bool:
    """spec like '08:00-23:00' (may wrap midnight, e.g. '20:00-02:00'). Empty = always."""
    spec = spec if spec is not None else get_settings().get("behavior", {}).get("working_hours", "")
    if not spec or "-" not in spec:
        return True
    now = now or datetime.now()
    try:
        start_s, end_s = [x.strip() for x in spec.split("-", 1)]
        sh, sm = map(int, start_s.split(":"))
        eh, em = map(int, end_s.split(":"))
    except ValueError:
        return True
    cur = now.hour * 60 + now.minute
    start, end = sh * 60 + sm, eh * 60 + em
    if start <= end:
        return start <= cur < end
    return cur >= start or cur < end


rate_limiter = RateLimiter()
