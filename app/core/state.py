"""Runtime settings (YAML defaults + DB overrides), pause flag and activity log."""
from __future__ import annotations

import logging
import threading
from typing import Any

from app.config import deep_merge, load_default_settings
from app.db import Activity, Setting, session_scope

log = logging.getLogger("agent")

_SETTINGS_KEY = "settings"
_PAUSED_KEY = "agent.paused"
_lock = threading.Lock()
_cache: dict[str, Any] | None = None


def get_settings() -> dict[str, Any]:
    global _cache
    with _lock:
        if _cache is None:
            with session_scope() as s:
                row = s.get(Setting, _SETTINGS_KEY)
                overrides = row.value if row else {}
            _cache = deep_merge(load_default_settings(), overrides or {})
        return _cache


def save_settings(new_values: dict[str, Any]) -> dict[str, Any]:
    """Persist overrides (merged with current overrides)."""
    global _cache
    with _lock:
        with session_scope() as s:
            row = s.get(Setting, _SETTINGS_KEY)
            current = row.value if row else {}
            merged = deep_merge(current or {}, new_values)
            if row:
                row.value = merged
            else:
                s.add(Setting(key=_SETTINGS_KEY, value=merged))
        _cache = None
    return get_settings()


def setting(path: str, default: Any = None) -> Any:
    node: Any = get_settings()
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


def is_paused() -> bool:
    with session_scope() as s:
        row = s.get(Setting, _PAUSED_KEY)
        return bool(row.value) if row else False


def set_paused(paused: bool) -> None:
    with session_scope() as s:
        row = s.get(Setting, _PAUSED_KEY)
        if row:
            row.value = paused
        else:
            s.add(Setting(key=_PAUSED_KEY, value=paused))
    log_activity("agent", "Agent to'xtatildi ⏸" if paused else "Agent ishga tushirildi ▶")


def log_activity(kind: str, message: str, level: str = "info") -> None:
    getattr(log, level if level in ("info", "warning", "error") else "info")(f"[{kind}] {message}")
    try:
        with session_scope() as s:
            s.add(Activity(kind=kind, message=message[:4000], level=level))
    except Exception:  # never let logging break the agent
        log.exception("activity log failed")
