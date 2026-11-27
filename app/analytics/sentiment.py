"""Comment sentiment analysis, spam moderation, and multilingual auto-replies for YouTube & Instagram."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.core import brain, repo, runtime
from app.core.brain import HistoryItem
from app.core.state import get_settings, is_paused, log_activity
from app.db import SocialComment, session_scope, utcnow


class SentimentResult(BaseModel):
    sentiment: Literal["positive", "neutral", "negative", "spam"]
    score: float = Field(description="-1.0 (very negative) to +1.0 (very positive); 0 for neutral/spam")
    language: str = Field(description="ISO code e.g. uz, ru, en")
    is_complaint: bool = Field(description="true if user reports a defect, wrong info, bad service or price complaint")
    summary: str = Field(description="Short Uzbek summary of the user's feedback")


async def analyze_sentiment(text: str) -> SentimentResult:
    llm = runtime.require_llm()
    prompt = f"""Analyze this social media comment for sentiment, spam, and language.
Comment: «{text[:1500]}»"""
    return await llm.generate_json(prompt, SentimentResult, temperature=0.2)


def comment_to_dict(c: SocialComment) -> dict[str, Any]:
    return {
        "id": c.id,
        "platform": c.platform,
        "external_id": c.external_id,
        "post_external_id": c.post_external_id,
        "author": c.author,
        "text": c.text,
        "language": c.language,
        "sentiment": c.sentiment,
        "sentiment_score": round(c.sentiment_score or 0.0, 2),
        "reply_text": c.reply_text,
        "status": c.status,
        "created_at": c.created_at.isoformat() + "Z" if c.created_at else None,
        "replied_at": c.replied_at.isoformat() + "Z" if c.replied_at else None,
    }


def list_comments(platform: str | None = None, limit: int = 80) -> list[dict[str, Any]]:
    with session_scope() as s:
        q = s.query(SocialComment)
        if platform:
            q = q.filter(SocialComment.platform == platform)
        return [comment_to_dict(c) for c in q.order_by(SocialComment.id.desc()).limit(limit).all()]


def _seen_comment(platform: str, external_id: str) -> bool:
    with session_scope() as s:
        return (
            s.query(SocialComment.id)
            .filter(SocialComment.platform == platform, SocialComment.external_id == external_id)
            .first()
            is not None
        )


async def handle_comment(platform: str, item: dict[str, Any]) -> dict[str, Any] | None:
    """Analyze one comment, moderate spam, reply in user's language, or escalate if unknown."""
    ext_id = str(item["external_id"])
    if _seen_comment(platform, ext_id):
        return None
    text = (item.get("text") or "").strip()
    if not text:
        return None

    scfg = get_settings().get("social", {})
    sent = await analyze_sentiment(text)

    with session_scope() as s:
        row = SocialComment(
            platform=platform,
            external_id=ext_id,
            post_external_id=str(item.get("post_external_id", "")),
            author=str(item.get("author", "User"))[:255],
            text=text,
            language=sent.language,
            sentiment=sent.sentiment,
            sentiment_score=max(-1.0, min(1.0, sent.score)),
            status="new",
        )
        s.add(row)
        s.flush()
        cid = row.id

    # 1. Auto-hide spam/toxic comments
    if sent.sentiment == "spam" and scfg.get("auto_hide_spam", True):
        try:
            if platform == "youtube" and runtime.youtube and runtime.youtube.configured:
                await runtime.youtube.moderate_comment(ext_id, reject=True)
            elif platform == "instagram" and runtime.instagram and runtime.instagram.configured:
                await runtime.instagram.hide_comment(ext_id)
            with session_scope() as s:
                s.get(SocialComment, cid).status = "moderated"
        except Exception as e:
            log_activity("analytics", f"Spam moderatsiyada xato ({platform}): {e}", "warning")
        return comment_to_dict(_get_row(cid))

    # 2. Decide reply using the agent brain (grounded in KB, mirrors user's language)
    res = await brain.decide_reply(
        chat_title=f"{platform.title()} izoh",
        context="comment",
        history=[],
        new_messages=[HistoryItem(author=item.get("author", "User"), text=text)],
        extra_context=f"Platform: {platform}. Sentiment: {sent.sentiment} ({sent.score:+.2f}).",
    )
    d = res.decision

    if res.escalate or sent.is_complaint:
        await repo.create_escalation(
            chat_id=0,
            chat_title=f"{platform.title()} izoh ({item.get('author', 'User')})",
            tg_message_id=None,
            sender_name=str(item.get("author", "User")),
            question=text,
            language=d.language or sent.language,
            reason=d.reason or ("Shikoyat / salbiy izoh" if sent.is_complaint else "Bazada javob topilmadi"),
        )

    if d.should_reply and d.reply.strip() and scfg.get("auto_reply_comments", True):
        try:
            if platform == "youtube" and runtime.youtube and runtime.youtube.configured:
                await runtime.youtube.reply_comment(ext_id, d.reply)
            elif platform == "instagram" and runtime.instagram and runtime.instagram.configured:
                await runtime.instagram.reply_comment(ext_id, d.reply)
            with session_scope() as s:
                r = s.get(SocialComment, cid)
                r.reply_text = d.reply
                r.status = "replied"
                r.replied_at = utcnow()
        except Exception as e:
            log_activity("analytics", f"{platform} izohiga javob yuborilmadi: {e}", "error")
    elif res.escalate:
        with session_scope() as s:
            s.get(SocialComment, cid).status = "escalated"
    else:
        with session_scope() as s:
            s.get(SocialComment, cid).status = "ignored"

    return comment_to_dict(_get_row(cid))


def _get_row(cid: int) -> SocialComment:
    with session_scope() as s:
        return s.get(SocialComment, cid)  # type: ignore[return-value]


async def poll_all_comments() -> int:
    """Poll YouTube and Instagram for new comments and respond/moderate automatically."""
    if is_paused() or not runtime.llm:
        return 0
    processed = 0
    if runtime.youtube and runtime.youtube.configured:
        try:
            for item in await runtime.youtube.fetch_recent_comments():
                if await handle_comment("youtube", item):
                    processed += 1
        except Exception as e:
            log_activity("youtube", f"Izohlarni olishda xato: {e}", "warning")
    if runtime.instagram and runtime.instagram.configured:
        try:
            for item in await runtime.instagram.fetch_recent_comments():
                if await handle_comment("instagram", item):
                    processed += 1
        except Exception as e:
            log_activity("instagram", f"Izohlarni olishda xato: {e}", "warning")
    return processed
