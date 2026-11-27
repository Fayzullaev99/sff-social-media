"""Channel content: AI post drafts, approval flow, scheduling and publishing."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import func

from app.approvals import service as approvals
from app.core import repo, runtime
from app.core.state import get_settings, log_activity
from app.db import KnowledgeChunk, KnowledgeDoc, Post, session_scope, utcnow
from app.knowledge import store


class PostDraft(BaseModel):
    topic: str = Field(description="Short topic title in Uzbek")
    text: str = Field(description="Ready-to-publish Telegram post text")


def post_to_dict(p: Post) -> dict[str, Any]:
    return {
        "id": p.id,
        "platform": p.platform,
        "channel_id": p.channel_id,
        "channel_title": p.channel_title,
        "topic": p.topic,
        "text": p.text,
        "media_path": p.media_path,
        "status": p.status,
        "scheduled_at": p.scheduled_at.isoformat() + "Z" if p.scheduled_at else None,
        "published_at": p.published_at.isoformat() + "Z" if p.published_at else None,
        "external_id": p.external_id,
        "approval_id": p.approval_id,
        "error": p.error,
        "created_at": p.created_at.isoformat() + "Z" if p.created_at else None,
    }


def to_utc_naive(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def list_posts(limit: int = 100) -> list[dict[str, Any]]:
    with session_scope() as s:
        return [post_to_dict(p) for p in s.query(Post).order_by(Post.id.desc()).limit(limit).all()]


def get_post(post_id: int) -> dict[str, Any] | None:
    with session_scope() as s:
        p = s.get(Post, post_id)
        return post_to_dict(p) if p else None


def _random_knowledge(n: int = 4) -> list[str]:
    with session_scope() as s:
        rows = (
            s.query(KnowledgeChunk.text, KnowledgeDoc.title)
            .join(KnowledgeDoc, KnowledgeDoc.id == KnowledgeChunk.doc_id)
            .filter(KnowledgeDoc.kind != "admin_answer")
            .order_by(func.random())
            .limit(n)
            .all()
        )
    return [f"(source: {t})\n{c}" for c, t in rows]


def _recent_topics(n: int = 15) -> list[str]:
    with session_scope() as s:
        return [t for (t,) in s.query(Post.topic).order_by(Post.id.desc()).limit(n).all() if t]


async def generate_post_text(topic: str | None, channel_title: str, instructions: str = "") -> PostDraft:
    llm = runtime.require_llm()
    p = get_settings().get("persona", {})
    lang = get_settings().get("content", {}).get("default_post_language", p.get("default_language", "uz"))
    if topic:
        knowledge = [f"(source: {h.doc_title})\n{h.text}" for h in await store.search(topic, k=5)]
    else:
        knowledge = _random_knowledge()
    recent = _recent_topics()
    learned = get_settings().get("content", {}).get("learned_guidance", "")
    prompt = f"""Write ONE engaging Telegram channel post for the channel "{channel_title}".
Author: {p.get('owner_name')} — {p.get('role')}
Style: {p.get('style')}
Language: {lang} (Uzbek in Latin script unless told otherwise)
Topic: {topic or 'choose the most useful/interesting topic from KNOWLEDGE'}
{('Extra instructions: ' + instructions) if instructions else ''}
{('Audience feedback self-correction guidance: ' + learned) if learned else ''}

Rules:
- Facts (prices, features, dates, contacts) ONLY from KNOWLEDGE. Never invent facts.
- Strong first line (hook), short paragraphs, 2–5 fitting emojis, a soft call to action at the end.
- 400–1200 characters. Telegram markdown only: **bold**, __italic__. No # headings.
- Avoid repeating these recent topics: {', '.join(recent) or '-'}

KNOWLEDGE:
{chr(10).join(knowledge) or '(empty — write a general, useful post without specific facts)'}"""
    return await llm.generate_json(prompt, PostDraft, temperature=0.9)


async def create_post(
    channel_id: int,
    *,
    topic: str | None = None,
    text: str | None = None,
    scheduled_at: datetime | None = None,
    media_path: str | None = None,
    instructions: str = "",
) -> dict[str, Any]:
    channel = repo.get_chat(channel_id)
    if not channel or channel["kind"] != "channel":
        raise ValueError("Kanal topilmadi yoki ruxsat berilmagan (Chatlar bo'limida kanalni yoqing)")
    if text is None:
        draft = await generate_post_text(topic, channel["title"], instructions)
        topic, text = draft.topic, draft.text
    with session_scope() as s:
        post = Post(
            channel_id=channel_id,
            channel_title=channel["title"],
            topic=(topic or text[:60])[:500],
            text=text,
            media_path=media_path,
            scheduled_at=to_utc_naive(scheduled_at),
            status="pending",
        )
        s.add(post)
        s.flush()
        post_id = post.id
    approval_id = await approvals.request(
        "publish_post", f"{channel['title']}: {topic or text[:60]}", {"post_id": post_id, "preview": text}
    )
    with session_scope() as s:
        s.get(Post, post_id).approval_id = approval_id
    return get_post(post_id)  # type: ignore[return-value]


def update_post_text(post_id: int, text: str, scheduled_at: datetime | None = None) -> dict[str, Any]:
    with session_scope() as s:
        p = s.get(Post, post_id)
        if not p or p.status not in ("pending", "scheduled"):
            raise ValueError("Faqat kutilayotgan postni tahrirlash mumkin")
        p.text = text
        if scheduled_at is not None:
            p.scheduled_at = to_utc_naive(scheduled_at)
        approval_id = p.approval_id
    if approval_id:
        a = approvals.get(approval_id)
        if a:
            approvals.update_payload(approval_id, {**a["payload"], "preview": text})
    return get_post(post_id)  # type: ignore[return-value]


async def regenerate_post(post_id: int, instructions: str = "") -> dict[str, Any]:
    post = get_post(post_id)
    if not post or post["status"] != "pending":
        raise ValueError("Faqat kutilayotgan postni qayta yozish mumkin")
    draft = await generate_post_text(post["topic"], post["channel_title"], instructions)
    with session_scope() as s:
        p = s.get(Post, post_id)
        p.text = draft.text
    if post["approval_id"]:
        a = approvals.get(post["approval_id"])
        if a:
            approvals.update_payload(post["approval_id"], {**a["payload"], "preview": draft.text})
    log_activity("content", f"Post #{post_id} qayta yozildi")
    return get_post(post_id)  # type: ignore[return-value]


async def publish_post(post_id: int) -> str:
    post = get_post(post_id)
    if not post:
        raise KeyError(f"Post #{post_id} topilmadi")
    if not runtime.userbot or not runtime.userbot.connected:
        raise RuntimeError("Telegram userbot ulanmagan")
    try:
        msg_id = await runtime.userbot.publish(post["channel_id"], post["text"], post["media_path"])
    except Exception as e:
        with session_scope() as s:
            p = s.get(Post, post_id)
            p.status, p.error = "failed", str(e)
        log_activity("content", f"Post #{post_id} joylanmadi: {e}", "error")
        raise
    with session_scope() as s:
        p = s.get(Post, post_id)
        p.status, p.published_at, p.external_id, p.error = "published", utcnow(), str(msg_id), None
    log_activity("content", f"📢 Post #{post_id} «{post['channel_title']}» kanaliga joylandi")
    return f"Joylandi (msg {msg_id})"


async def publish_due_posts() -> int:
    now = utcnow()
    with session_scope() as s:
        due = [p.id for p in s.query(Post).filter(Post.status == "scheduled", Post.scheduled_at <= now).all()]
    for pid in due:
        try:
            await publish_post(pid)
        except Exception:
            pass
    return len(due)


@approvals.on_approve("publish_post")
async def _on_post_approved(payload: dict[str, Any], approval_id: int) -> str:
    post_id = int(payload["post_id"])
    post = get_post(post_id)
    if not post:
        raise KeyError(f"Post #{post_id} topilmadi")
    with session_scope() as s:
        p = s.get(Post, post_id)
        if p.scheduled_at and p.scheduled_at > utcnow():
            p.status = "scheduled"
            return f"Rejalashtirildi: {p.scheduled_at.isoformat()} UTC"
    return await publish_post(post_id)


@approvals.on_reject("publish_post")
async def _on_post_rejected(payload: dict[str, Any], approval_id: int) -> str:
    with session_scope() as s:
        p = s.get(Post, int(payload["post_id"]))
        if p:
            p.status = "rejected"
    return "Rad etildi"
