"""Small data-access helpers for chats, messages and escalations."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func

from app.core import runtime
from app.core.state import log_activity
from app.db import Chat, Escalation, Message, session_scope, utcnow


# ---------------------------------------------------------------- chats
def chat_to_dict(c: Chat) -> dict[str, Any]:
    return {
        "id": c.id,
        "title": c.title,
        "username": c.username,
        "kind": c.kind,
        "allowed": c.allowed,
        "mode": c.mode,
        "linked_chat_id": c.linked_chat_id,
        "notes": c.notes,
    }


def get_chat(chat_id: int) -> dict[str, Any] | None:
    with session_scope() as s:
        c = s.get(Chat, chat_id)
        return chat_to_dict(c) if c else None


def get_allowed_chat(chat_id: int) -> dict[str, Any] | None:
    c = get_chat(chat_id)
    return c if c and c["allowed"] else None


def list_chats() -> list[dict[str, Any]]:
    with session_scope() as s:
        return [chat_to_dict(c) for c in s.query(Chat).order_by(Chat.allowed.desc(), Chat.title).all()]


def upsert_chat(chat_id: int, **fields: Any) -> dict[str, Any]:
    allowed_fields = {"title", "username", "kind", "allowed", "mode", "linked_chat_id", "notes"}
    with session_scope() as s:
        c = s.get(Chat, chat_id)
        if c is None:
            c = Chat(id=chat_id)
            s.add(c)
        for k, v in fields.items():
            if k in allowed_fields and v is not None:
                setattr(c, k, v)
        s.flush()
        return chat_to_dict(c)


def delete_chat(chat_id: int) -> None:
    with session_scope() as s:
        c = s.get(Chat, chat_id)
        if c:
            s.delete(c)


def allowed_channels() -> list[dict[str, Any]]:
    with session_scope() as s:
        rows = s.query(Chat).filter(Chat.allowed.is_(True), Chat.kind == "channel").all()
        return [chat_to_dict(c) for c in rows]


# ---------------------------------------------------------------- messages
def log_message(
    chat_id: int,
    direction: str,
    text: str,
    *,
    tg_message_id: int | None = None,
    sender_id: int | None = None,
    sender_name: str = "",
    language: str | None = None,
    meta: dict | None = None,
) -> int:
    with session_scope() as s:
        m = Message(
            chat_id=chat_id,
            direction=direction,
            text=text,
            tg_message_id=tg_message_id,
            sender_id=sender_id,
            sender_name=sender_name,
            language=language,
            meta=meta or {},
        )
        s.add(m)
        s.flush()
        return m.id


def recent_messages(chat_id: int, limit: int = 20, exclude_ids: set[int] | None = None) -> list[dict[str, Any]]:
    with session_scope() as s:
        q = s.query(Message).filter(Message.chat_id == chat_id)
        if exclude_ids:
            q = q.filter(Message.id.notin_(exclude_ids))
        rows = q.order_by(Message.id.desc()).limit(limit).all()
        return [
            {
                "id": m.id,
                "direction": m.direction,
                "text": m.text,
                "sender_name": m.sender_name,
                "tg_message_id": m.tg_message_id,
                "language": m.language,
                "created_at": m.created_at.isoformat(),
            }
            for m in reversed(rows)
        ]


def message_stats(since: datetime | None = None) -> dict[str, int]:
    since = since or (utcnow() - timedelta(days=1))
    with session_scope() as s:
        rows = (
            s.query(Message.direction, func.count(Message.id))
            .filter(Message.created_at >= since)
            .group_by(Message.direction)
            .all()
        )
    out = {"in": 0, "out": 0, "owner": 0}
    out.update({d: n for d, n in rows})
    return out


# ---------------------------------------------------------------- escalations
def escalation_to_dict(e: Escalation) -> dict[str, Any]:
    return {
        "id": e.id,
        "chat_id": e.chat_id,
        "chat_title": e.chat_title,
        "tg_message_id": e.tg_message_id,
        "sender_name": e.sender_name,
        "question": e.question,
        "language": e.language,
        "reason": e.reason,
        "status": e.status,
        "answer": e.answer,
        "created_at": e.created_at.isoformat() if e.created_at else None,
        "answered_at": e.answered_at.isoformat() if e.answered_at else None,
    }


async def create_escalation(
    *,
    chat_id: int,
    chat_title: str,
    tg_message_id: int | None,
    sender_name: str,
    question: str,
    language: str,
    reason: str,
) -> int:
    with session_scope() as s:
        e = Escalation(
            chat_id=chat_id,
            chat_title=chat_title,
            tg_message_id=tg_message_id,
            sender_name=sender_name,
            question=question,
            language=language or "uz",
            reason=reason,
        )
        s.add(e)
        s.flush()
        esc_id = e.id
    log_activity("escalation", f"❓ Adminga savol #{esc_id} ({chat_title}): {question[:120]}", "warning")
    await runtime.publish("escalation.created", esc_id)
    return esc_id


def get_escalation(esc_id: int) -> dict[str, Any] | None:
    with session_scope() as s:
        e = s.get(Escalation, esc_id)
        return escalation_to_dict(e) if e else None


def list_escalations(status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    with session_scope() as s:
        q = s.query(Escalation)
        if status:
            q = q.filter(Escalation.status == status)
        return [escalation_to_dict(e) for e in q.order_by(Escalation.id.desc()).limit(limit).all()]


async def answer_escalation(esc_id: int, answer: str, by: str) -> dict[str, Any]:
    """Deliver the owner's answer to the user and teach the knowledge base."""
    from app.core import brain
    from app.core.state import setting
    from app.knowledge import store

    esc = get_escalation(esc_id)
    if esc is None:
        raise KeyError(f"#{esc_id} topilmadi")
    if esc["status"] != "open":
        return esc

    text = answer
    if setting("behavior.polish_admin_answers", True) and runtime.llm:
        try:
            text = await brain.polish_admin_answer(esc["question"], answer, esc["language"])
        except Exception as ex:  # fall back to raw answer
            log_activity("escalation", f"Javobni moslashda xato: {ex}", "warning")

    if runtime.userbot and runtime.userbot.connected:
        await runtime.userbot.send_humanlike(esc["chat_id"], text, reply_to=esc["tg_message_id"], quick=True)
    else:
        raise RuntimeError("Telegram userbot ulanmagan — javob yuborib bo'lmadi")

    with session_scope() as s:
        e = s.get(Escalation, esc_id)
        e.status = "answered"
        e.answer = answer
        e.answered_at = utcnow()

    # Learn: save Q&A so next time the agent can answer by itself
    try:
        await store.add_document(
            f"Savol-javob: {esc['question'][:80]}",
            f"Savol: {esc['question']}\nJavob: {answer}",
            source=f"escalation#{esc_id}",
            kind="admin_answer",
        )
    except Exception as ex:
        log_activity("knowledge", f"Admin javobini bazaga qo'shishda xato: {ex}", "warning")

    log_activity("escalation", f"✅ #{esc_id} javob berildi ({by})")
    return get_escalation(esc_id)  # type: ignore[return-value]


def dismiss_escalation(esc_id: int) -> None:
    with session_scope() as s:
        e = s.get(Escalation, esc_id)
        if e and e.status == "open":
            e.status = "dismissed"
            e.answered_at = utcnow()
    log_activity("escalation", f"#{esc_id} yopildi")
