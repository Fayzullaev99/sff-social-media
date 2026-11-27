"""Human-in-the-loop approval queue.

Every action that needs a human decision (publishing content, sending a reply in "approve" mode,
and ANY money-spending action) is stored as an Approval and executed only after a decision
from the admin bot or the dashboard.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from app.core import runtime
from app.core.policy import MoneyActionBlocked, is_money_kind
from app.core.state import log_activity
from app.db import Approval, session_scope, utcnow

Handler = Callable[[dict[str, Any], int], Awaitable[str]]

_on_approve: dict[str, Handler] = {}
_on_reject: dict[str, Handler] = {}

KIND_LABELS = {
    "publish_post": "📢 Kanalga post",
    "publish_video": "🎬 Video joylash",
    "send_reply": "💬 Javob yuborish",
    "ad_campaign_launch": "💰 Reklama kampaniyasini ishga tushirish",
    "ad_budget_change": "💰 Reklama byudjetini o'zgartirish",
    "ad_campaign_resume": "💰 Reklamani qayta yoqish",
    "paid_promotion": "💰 Pullik reklama",
    "paid_service": "💰 Pullik xizmat",
}


def on_approve(kind: str):
    def deco(fn: Handler) -> Handler:
        _on_approve[kind] = fn
        return fn

    return deco


def on_reject(kind: str):
    def deco(fn: Handler) -> Handler:
        _on_reject[kind] = fn
        return fn

    return deco


def to_dict(a: Approval) -> dict[str, Any]:
    return {
        "id": a.id,
        "kind": a.kind,
        "kind_label": KIND_LABELS.get(a.kind, a.kind),
        "title": a.title,
        "payload": a.payload,
        "requires_money": a.requires_money,
        "amount": a.amount,
        "currency": a.currency,
        "status": a.status,
        "decided_by": a.decided_by,
        "result": a.result,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "decided_at": a.decided_at.isoformat() if a.decided_at else None,
    }


def get(approval_id: int) -> dict[str, Any] | None:
    with session_scope() as s:
        a = s.get(Approval, approval_id)
        return to_dict(a) if a else None


async def request(
    kind: str,
    title: str,
    payload: dict[str, Any],
    *,
    amount: float | None = None,
    currency: str | None = None,
) -> int:
    requires_money = is_money_kind(kind) or bool(amount and amount > 0)
    with session_scope() as s:
        a = Approval(
            kind=kind,
            title=title[:500],
            payload=payload,
            requires_money=requires_money,
            amount=amount,
            currency=currency,
        )
        s.add(a)
        s.flush()
        approval_id = a.id
    log_activity("approval", f"Tasdiq so'raldi #{approval_id}: {KIND_LABELS.get(kind, kind)} — {title}")
    await runtime.publish("approval.created", approval_id)
    return approval_id


def update_payload(approval_id: int, payload: dict[str, Any], title: str | None = None) -> None:
    with session_scope() as s:
        a = s.get(Approval, approval_id)
        if a and a.status == "pending":
            a.payload = dict(payload)
            if title is not None:
                a.title = title[:500]


async def decide(approval_id: int, approve: bool, decided_by: str) -> dict[str, Any]:
    """Record a HUMAN decision and execute the action if approved."""
    if not decided_by:
        raise MoneyActionBlocked("Qaror faqat inson tomonidan qabul qilinishi mumkin")
    with session_scope() as s:
        a = s.get(Approval, approval_id)
        if a is None:
            raise KeyError(f"Approval #{approval_id} topilmadi")
        if a.status != "pending":
            return to_dict(a)
        a.status = "approved" if approve else "rejected"
        a.decided_by = decided_by
        a.decided_at = utcnow()
        kind, payload = a.kind, dict(a.payload or {})

    log_activity(
        "approval",
        f"#{approval_id} {'✅ tasdiqlandi' if approve else '❌ rad etildi'} ({decided_by})",
    )
    if approve:
        await _execute(approval_id)
    else:
        handler = _on_reject.get(kind)
        if handler:
            try:
                await handler(payload, approval_id)
            except Exception as e:  # pragma: no cover - defensive
                log_activity("approval", f"#{approval_id} rad etish ishlovchisida xato: {e}", "error")
    result = get(approval_id)
    await runtime.publish("approval.decided", result)
    return result  # type: ignore[return-value]


async def _execute(approval_id: int) -> None:
    with session_scope() as s:
        a = s.get(Approval, approval_id)
        if a is None or a.status != "approved" or not a.decided_by:
            # The money guard: nothing runs without an explicit, recorded human approval.
            raise MoneyActionBlocked(f"#{approval_id} tasdiqlanmagan — bajarilmaydi")
        kind, payload = a.kind, dict(a.payload or {})

    handler = _on_approve.get(kind)
    status, result = "executed", "OK"
    if handler is None:
        status, result = "failed", f"'{kind}' uchun ishlovchi hali ulanmagan"
    else:
        try:
            result = await handler(payload, approval_id) or "OK"
        except Exception as e:
            status, result = "failed", f"{type(e).__name__}: {e}"
    with session_scope() as s:
        a = s.get(Approval, approval_id)
        a.status = status
        a.result = str(result)[:4000]
    log_activity("approval", f"#{approval_id} {'bajarildi' if status == 'executed' else 'XATO'}: {result}",
                 "info" if status == "executed" else "error")
