"""Performance analytics, audience feedback monitoring, quality rating, and self-correction."""
from __future__ import annotations

from datetime import timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import func

from app.core import repo, runtime
from app.core.state import get_settings, log_activity, save_settings
from app.db import FeedbackInsight, MetricSnapshot, SocialComment, session_scope, utcnow


class QualityAudit(BaseModel):
    quality_rating: float = Field(description="Overall content & service quality score from 1.0 to 10.0")
    summary_uz: str = Field(description="Concise summary of audience feedback, ratings and trends in Uzbek")
    issues_uz: list[str] = Field(description="Key complaints, weak content patterns or mistakes noticed (in Uzbek)")
    self_correction_guidance: str = Field(
        description="Concrete instruction (1-3 sentences) for future posts/videos/replies to fix issues and improve engagement"
    )
    severity: Literal["info", "warning", "critical"] = Field(
        description="critical if major negative backlash/factual error; warning if engagement or rating drops; else info"
    )
    notify_admin: bool = Field(description="true if admin should be alerted immediately via Telegram")


async def collect_metrics() -> list[dict[str, Any]]:
    """Capture metric snapshots from all connected platforms."""
    saved: list[dict[str, Any]] = []

    # Calculate average sentiment per platform over the last 7 days
    week_ago = utcnow() - timedelta(days=7)
    with session_scope() as s:
        sent_rows = (
            s.query(SocialComment.platform, func.avg(SocialComment.sentiment_score))
            .filter(SocialComment.created_at >= week_ago, SocialComment.sentiment != "spam")
            .group_by(SocialComment.platform)
            .all()
        )
    avg_sent = {p: float(v or 0.0) for p, v in sent_rows}

    # Telegram snapshot
    st = repo.message_stats(week_ago)
    with session_scope() as s:
        snap = MetricSnapshot(
            platform="telegram",
            title="Telegram",
            followers=sum(1 for c in repo.list_chats() if c["allowed"]),
            views=st["in"],
            likes=st["out"],
            comments_count=st["in"],
            engagement_rate=round(st["out"] / max(st["in"], 1) * 100, 1),
            avg_sentiment=avg_sent.get("telegram", 0.5),
            raw=st,
        )
        s.add(snap)
        s.flush()
        saved.append(_snap_dict(snap))

    # YouTube snapshot
    if runtime.youtube and runtime.youtube.configured:
        try:
            ys = await runtime.youtube.fetch_channel_stats()
            if ys:
                vids = ys.get("recent_videos", [])
                v_views = sum(v["views"] for v in vids)
                v_likes = sum(v["likes"] for v in vids)
                v_comm = sum(v["comments"] for v in vids)
                er = round((v_likes + v_comm) / max(v_views, 1) * 100, 2)
                with session_scope() as s:
                    snap = MetricSnapshot(
                        platform="youtube",
                        title=ys["title"],
                        followers=ys["followers"],
                        views=ys["views"],
                        likes=v_likes,
                        comments_count=v_comm,
                        engagement_rate=er,
                        avg_sentiment=avg_sent.get("youtube", 0.0),
                        raw=ys,
                    )
                    s.add(snap)
                    s.flush()
                    saved.append(_snap_dict(snap))
        except Exception as e:
            log_activity("analytics", f"YouTube metrikalari olinmadi: {e}", "warning")

    # Instagram snapshot
    if runtime.instagram and runtime.instagram.configured:
        try:
            igs = await runtime.instagram.fetch_account_stats()
            if igs:
                er = round((igs["likes"] + igs["comments"]) / max(igs["followers"], 1) * 100, 2)
                with session_scope() as s:
                    snap = MetricSnapshot(
                        platform="instagram",
                        title=igs["title"],
                        followers=igs["followers"],
                        views=0,
                        likes=igs["likes"],
                        comments_count=igs["comments"],
                        engagement_rate=er,
                        avg_sentiment=avg_sent.get("instagram", 0.0),
                        raw=igs,
                    )
                    s.add(snap)
                    s.flush()
                    saved.append(_snap_dict(snap))
        except Exception as e:
            log_activity("analytics", f"Instagram metrikalari olinmadi: {e}", "warning")

    return saved


async def run_quality_audit() -> dict[str, Any]:
    """Evaluate ratings, comments and audience feedback; self-correct content strategy if needed."""
    llm = runtime.require_llm()
    week_ago = utcnow() - timedelta(days=7)
    with session_scope() as s:
        comments = (
            s.query(SocialComment)
            .filter(SocialComment.created_at >= week_ago)
            .order_by(SocialComment.id.desc())
            .limit(40)
            .all()
        )
        snaps = (
            s.query(MetricSnapshot)
            .order_by(MetricSnapshot.id.desc())
            .limit(12)
            .all()
        )
        comment_lines = [
            f"[{c.platform} | {c.sentiment} ({c.sentiment_score:+.2f})] {c.author}: {c.text[:220]}"
            for c in comments
        ]
        snap_lines = [
            f"[{m.platform}] followers={m.followers}, views={m.views}, likes={m.likes}, comments={m.comments_count}, ER={m.engagement_rate}%"
            for m in snaps
        ]

    prompt = f"""You are a social media quality & reputation director.
Review the latest metrics and follower comments below, calculate an honest quality_rating (1..10),
identify complaints or drop in quality, and write concrete self-correction guidance for future posts and videos.

RECENT METRICS:
{chr(10).join(snap_lines) or '(no metrics yet)'}

RECENT FOLLOWER COMMENTS & FEEDBACK:
{chr(10).join(comment_lines) or '(no comments yet — give baseline score 7.5 and constructive starter guidance)'}"""

    audit = await llm.generate_json(prompt, QualityAudit, temperature=0.3)

    auto_apply = bool(get_settings().get("social", {}).get("auto_self_correct", True))
    action_taken = ""
    if auto_apply and audit.self_correction_guidance.strip():
        save_settings({
            "content": {"learned_guidance": audit.self_correction_guidance.strip()},
            "analytics": {"last_quality_rating": round(audit.quality_rating, 1)},
        })
        action_taken = f"Kontent strategiyasi avtomatik yangilandi: {audit.self_correction_guidance.strip()}"

    with session_scope() as s:
        ins = FeedbackInsight(
            platform="all",
            category="correction" if action_taken else "quality",
            severity=audit.severity,
            summary=f"Reyting: {audit.quality_rating:.1f}/10 — {audit.summary_uz}",
            action_taken=action_taken or ("; ".join(audit.issues_uz) if audit.issues_uz else "O'zgarish talab qilinmadi"),
            auto_applied=bool(action_taken),
        )
        s.add(ins)
        s.flush()
        insight_dict = _insight_dict(ins)

    log_activity(
        "analytics",
        f"📈 Sifat tahlili: {audit.quality_rating:.1f}/10 — {audit.summary_uz[:160]}",
        "warning" if audit.severity != "info" else "info",
    )

    if audit.notify_admin and runtime.admin_bot:
        issues_txt = "\n".join(f"• {x}" for x in audit.issues_uz[:5])
        await runtime.admin_bot.send_admins(
            f"⚠️ <b>Sifat va fikr-mulohaza ogohlantirishi</b>\n"
            f"⭐ Reyting: <b>{audit.quality_rating:.1f}/10</b>\n\n"
            f"{audit.summary_uz}\n\n"
            + (f"<b>Aniqlangan muammolar:</b>\n{issues_txt}\n\n" if issues_txt else "")
            + (f"🛠 <i>{action_taken}</i>" if action_taken else "")
        )

    return {**audit.model_dump(), "insight": insight_dict}


def _snap_dict(m: MetricSnapshot) -> dict[str, Any]:
    return {
        "id": m.id,
        "platform": m.platform,
        "title": m.title,
        "followers": m.followers,
        "views": m.views,
        "likes": m.likes,
        "comments_count": m.comments_count,
        "engagement_rate": m.engagement_rate,
        "avg_sentiment": round(m.avg_sentiment or 0.0, 2),
        "captured_at": m.captured_at.isoformat() + "Z" if m.captured_at else None,
    }


def _insight_dict(i: FeedbackInsight) -> dict[str, Any]:
    return {
        "id": i.id,
        "platform": i.platform,
        "category": i.category,
        "severity": i.severity,
        "summary": i.summary,
        "action_taken": i.action_taken,
        "auto_applied": i.auto_applied,
        "created_at": i.created_at.isoformat() + "Z" if i.created_at else None,
    }


def dashboard_summary() -> dict[str, Any]:
    with session_scope() as s:
        sent_counts = dict(
            s.query(SocialComment.sentiment, func.count(SocialComment.id))
            .group_by(SocialComment.sentiment)
            .all()
        )
        avg_score = s.query(func.avg(SocialComment.sentiment_score)).filter(SocialComment.sentiment != "spam").scalar()
        # Latest snapshot per platform
        latest_by_plat: dict[str, dict[str, Any]] = {}
        for m in s.query(MetricSnapshot).order_by(MetricSnapshot.id.desc()).limit(30).all():
            if m.platform not in latest_by_plat:
                latest_by_plat[m.platform] = _snap_dict(m)
        insights = [_insight_dict(i) for i in s.query(FeedbackInsight).order_by(FeedbackInsight.id.desc()).limit(20).all()]
        comments = [
            {
                "id": c.id, "platform": c.platform, "author": c.author, "text": c.text,
                "language": c.language, "sentiment": c.sentiment, "sentiment_score": round(c.sentiment_score or 0.0, 2),
                "reply_text": c.reply_text, "status": c.status,
                "created_at": c.created_at.isoformat() + "Z" if c.created_at else None,
            }
            for c in s.query(SocialComment).order_by(SocialComment.id.desc()).limit(30).all()
        ]
    rating = get_settings().get("analytics", {}).get("last_quality_rating")
    if rating is None:
        # Derive initial rating from sentiment score (-1..1 -> 1..10)
        rating = round(5.5 + float(avg_score or 0.4) * 4.5, 1)
    return {
        "quality_rating": rating,
        "avg_sentiment": round(float(avg_score or 0.0), 2),
        "sentiment_breakdown": {
            "positive": sent_counts.get("positive", 0),
            "neutral": sent_counts.get("neutral", 0),
            "negative": sent_counts.get("negative", 0),
            "spam": sent_counts.get("spam", 0),
        },
        "learned_guidance": get_settings().get("content", {}).get("learned_guidance", ""),
        "platforms": latest_by_plat,
        "insights": insights,
        "comments": comments,
    }
