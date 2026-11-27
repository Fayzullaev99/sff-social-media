"""Web dashboard: REST API + static single-page UI (HTTP Basic auth)."""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.approvals import service as approvals
from app.config import env
from app.core import repo, runtime
from app.core.brain import HistoryItem, decide_reply
from app.core.state import get_settings, is_paused, save_settings, set_paused
from app.db import Activity, AdCampaign, Approval, KnowledgeDoc, Post, VideoProject, session_scope, utcnow
from app.knowledge import store

STATIC_DIR = Path(__file__).parent / "static"
security = HTTPBasic()


def auth(creds: HTTPBasicCredentials = Depends(security)) -> str:
    ok_user = secrets.compare_digest(creds.username.encode(), env.dashboard_user.encode())
    ok_pass = secrets.compare_digest(creds.password.encode(), env.dashboard_password.encode())
    if not (ok_user and ok_pass):
        raise HTTPException(401, "Unauthorized", headers={"WWW-Authenticate": "Basic"})
    return creds.username


app = FastAPI(title="Social Agent", docs_url=None, redoc_url=None, dependencies=[Depends(auth)])


def _bad(e: Exception) -> HTTPException:
    return HTTPException(400, str(e))


# ---------------------------------------------------------------- overview
@app.get("/api/overview")
def overview() -> dict[str, Any]:
    st = repo.message_stats()
    week = repo.message_stats(utcnow() - timedelta(days=7))
    with session_scope() as s:
        docs = s.query(KnowledgeDoc).count()
        pending = s.query(Approval).filter(Approval.status == "pending").count()
        published = s.query(Post).filter(Post.status == "published").count()
        videos_count = s.query(VideoProject).count()
        active_ads = s.query(AdCampaign).filter(AdCampaign.status == "active").count()
        activity = [
            {"kind": a.kind, "level": a.level, "message": a.message, "created_at": a.created_at.isoformat() + "Z"}
            for a in s.query(Activity).order_by(Activity.id.desc()).limit(25).all()
        ]
    chats = repo.list_chats()
    ub, ab = runtime.userbot, runtime.admin_bot
    yt, ig = runtime.youtube, runtime.instagram
    me = getattr(ub, "me", None) if ub else None
    from app.ads.clients import google_ads, meta_ads

    return {
        "paused": is_paused(),
        "services": {
            "gemini": runtime.llm is not None,
            "telegram": bool(ub and ub.connected),
            "admin_bot": bool(ab and ab.connected),
            "telegram_user": (f"{me.first_name or ''} (@{me.username})" if me else None),
            "youtube": bool(yt and yt.configured),
            "youtube_channel": yt.channel_title if yt else None,
            "instagram": bool(ig and ig.configured),
            "instagram_user": f"@{ig.username}" if ig and ig.username else None,
            "meta_ads": meta_ads.configured,
            "google_ads": google_ads.configured,
        },
        "stats": {
            "messages_in_24h": st["in"],
            "replies_24h": st["out"],
            "messages_in_7d": week["in"],
            "replies_7d": week["out"],
            "allowed_chats": sum(1 for c in chats if c["allowed"]),
            "open_questions": len(repo.list_escalations("open")),
            "pending_approvals": pending,
            "knowledge_docs": docs,
            "published_posts": published,
            "videos": videos_count,
            "active_ads": active_ads,
            "quality_rating": get_settings().get("analytics", {}).get("last_quality_rating", 8.0),
        },
        "activity": activity,
    }


@app.post("/api/agent/{action}")
def agent_action(action: str) -> dict[str, Any]:
    if action not in ("pause", "resume"):
        raise HTTPException(404)
    set_paused(action == "pause")
    return {"paused": is_paused()}


# ---------------------------------------------------------------- chats
class ChatIn(BaseModel):
    id: int
    title: str = ""
    username: str | None = None
    kind: str = "user"
    allowed: bool | None = None
    mode: str | None = None
    notes: str | None = None


@app.get("/api/chats")
def chats() -> list[dict[str, Any]]:
    return repo.list_chats()


@app.get("/api/dialogs")
async def dialogs() -> list[dict[str, Any]]:
    if not runtime.userbot or not runtime.userbot.connected:
        raise HTTPException(503, "Telegram userbot ulanmagan")
    known = {c["id"]: c for c in repo.list_chats()}
    items = await runtime.userbot.list_dialogs()
    for d in items:
        k = known.get(d["id"])
        d["allowed"] = bool(k and k["allowed"])
        d["mode"] = k["mode"] if k else "auto"
    return items


@app.post("/api/chats")
async def upsert_chat(body: ChatIn) -> dict[str, Any]:
    fields = body.model_dump(exclude={"id"}, exclude_none=True)
    chat = repo.upsert_chat(body.id, **fields)
    # When a channel is allowed, also register its discussion group (for comment replies)
    if chat["kind"] == "channel" and body.allowed and runtime.userbot and runtime.userbot.connected:
        try:
            linked = await runtime.userbot.linked_discussion_id(body.id)
            if linked:
                repo.upsert_chat(body.id, linked_chat_id=linked)
                repo.upsert_chat(linked, title=f"{chat['title']} — izohlar", kind="discussion", allowed=True)
        except Exception:
            pass
    return repo.get_chat(body.id)  # type: ignore[return-value]


@app.delete("/api/chats/{chat_id}")
def delete_chat(chat_id: int) -> dict[str, bool]:
    repo.delete_chat(chat_id)
    return {"ok": True}


@app.get("/api/chats/{chat_id}/messages")
def chat_messages(chat_id: int, limit: int = 100) -> list[dict[str, Any]]:
    return repo.recent_messages(chat_id, limit)


# ---------------------------------------------------------------- knowledge
class TextDoc(BaseModel):
    title: str
    text: str


class UrlDoc(BaseModel):
    url: str


class Query(BaseModel):
    q: str


@app.get("/api/knowledge")
def knowledge() -> list[dict[str, Any]]:
    with session_scope() as s:
        return [
            {"id": d.id, "title": d.title, "source": d.source, "kind": d.kind, "chunks": d.chunk_count,
             "chars": d.char_count, "created_at": d.created_at.isoformat() + "Z"}
            for d in s.query(KnowledgeDoc).order_by(KnowledgeDoc.id.desc()).all()
        ]


@app.post("/api/knowledge/upload")
async def knowledge_upload(file: UploadFile = File(...)) -> dict[str, Any]:
    try:
        doc = await store.add_file(file.filename or "file.txt", await file.read())
    except Exception as e:
        raise _bad(e)
    return {"id": doc.id, "title": doc.title, "chunks": doc.chunk_count}


@app.post("/api/knowledge/text")
async def knowledge_text(body: TextDoc) -> dict[str, Any]:
    try:
        doc = await store.add_document(body.title, body.text, kind="text")
    except Exception as e:
        raise _bad(e)
    return {"id": doc.id, "title": doc.title, "chunks": doc.chunk_count}


@app.post("/api/knowledge/url")
async def knowledge_url(body: UrlDoc) -> dict[str, Any]:
    try:
        doc = await store.add_url(body.url)
    except Exception as e:
        raise _bad(e)
    return {"id": doc.id, "title": doc.title, "chunks": doc.chunk_count}


@app.delete("/api/knowledge/{doc_id}")
def knowledge_delete(doc_id: int) -> dict[str, bool]:
    return {"ok": store.delete_document(doc_id)}


@app.post("/api/knowledge/search")
async def knowledge_search(body: Query) -> list[dict[str, Any]]:
    try:
        hits = await store.search(body.q, k=6)
    except Exception as e:
        raise _bad(e)
    return [{"title": h.doc_title, "score": round(h.score, 3), "text": h.text} for h in hits]


# ---------------------------------------------------------------- playground
class PlaygroundIn(BaseModel):
    messages: list[dict[str, Any]]  # [{role: "user"|"agent", text}]
    context: str = "private"


@app.post("/api/playground")
async def playground(body: PlaygroundIn) -> dict[str, Any]:
    if not body.messages:
        raise HTTPException(400, "Xabar yo'q")
    items = [HistoryItem(author="Mijoz" if m.get("role") == "user" else "SEN", text=m.get("text", ""),
                         is_self=m.get("role") != "user") for m in body.messages]
    # trailing user messages are "new", the rest is history
    split = len(items)
    while split > 0 and not items[split - 1].is_self:
        split -= 1
    history, new = items[:split], items[split:] or items[-1:]
    try:
        r = await decide_reply(chat_title="Sinov (playground)", context=body.context,  # type: ignore[arg-type]
                               history=history, new_messages=new)
    except Exception as e:
        raise _bad(e)
    return {
        **r.decision.model_dump(),
        "escalate": r.escalate,
        "sources": [{"title": h.doc_title, "score": round(h.score, 3)} for h in r.hits[:4]],
    }


# ---------------------------------------------------------------- escalations
class AnswerIn(BaseModel):
    answer: str


@app.get("/api/escalations")
def escalations(status: str | None = None) -> list[dict[str, Any]]:
    return repo.list_escalations(status)


@app.post("/api/escalations/{esc_id}/answer")
async def answer(esc_id: int, body: AnswerIn, user: str = Depends(auth)) -> dict[str, Any]:
    try:
        return await repo.answer_escalation(esc_id, body.answer, by=f"web:{user}")
    except Exception as e:
        raise _bad(e)


@app.post("/api/escalations/{esc_id}/dismiss")
def dismiss(esc_id: int) -> dict[str, bool]:
    repo.dismiss_escalation(esc_id)
    return {"ok": True}


# ---------------------------------------------------------------- approvals
class DecideIn(BaseModel):
    approve: bool


@app.get("/api/approvals")
def list_approvals(status: str | None = None) -> list[dict[str, Any]]:
    with session_scope() as s:
        q = s.query(Approval)
        if status:
            q = q.filter(Approval.status == status)
        return [approvals.to_dict(a) for a in q.order_by(Approval.id.desc()).limit(100).all()]


@app.post("/api/approvals/{approval_id}/decide")
async def decide(approval_id: int, body: DecideIn, user: str = Depends(auth)) -> dict[str, Any]:
    try:
        return await approvals.decide(approval_id, body.approve, decided_by=f"web:{user}")
    except Exception as e:
        raise _bad(e)


# ---------------------------------------------------------------- posts
class PostIn(BaseModel):
    channel_id: int
    topic: str | None = None
    text: str | None = None
    instructions: str = ""
    scheduled_at: datetime | None = None


class PostEdit(BaseModel):
    text: str
    scheduled_at: datetime | None = None


class RegenIn(BaseModel):
    instructions: str = ""


@app.get("/api/posts")
def list_posts() -> list[dict[str, Any]]:
    from app.content import posts

    return posts.list_posts()


@app.post("/api/posts")
async def create_post(body: PostIn) -> dict[str, Any]:
    from app.content import posts

    try:
        return await posts.create_post(body.channel_id, topic=body.topic or None, text=body.text or None,
                                       scheduled_at=body.scheduled_at, instructions=body.instructions)
    except Exception as e:
        raise _bad(e)


@app.patch("/api/posts/{post_id}")
def edit_post(post_id: int, body: PostEdit) -> dict[str, Any]:
    from app.content import posts

    try:
        return posts.update_post_text(post_id, body.text, body.scheduled_at)
    except Exception as e:
        raise _bad(e)


@app.post("/api/posts/{post_id}/regenerate")
async def regenerate(post_id: int, body: RegenIn) -> dict[str, Any]:
    from app.content import posts

    try:
        return await posts.regenerate_post(post_id, body.instructions)
    except Exception as e:
        raise _bad(e)


# ---------------------------------------------------------------- videos
class VideoIn(BaseModel):
    topic: str | None = None
    style: str = "auto"
    aspect_ratio: str = "9:16"
    language: str = "uz"
    targets: list[str] = ["youtube", "instagram"]
    instructions: str = ""


@app.get("/api/videos")
def list_videos() -> list[dict[str, Any]]:
    from app.content.video import render as vr

    return vr.list_videos()


@app.post("/api/videos")
async def create_video(body: VideoIn) -> dict[str, Any]:
    from app.content.video import render as vr

    try:
        return await vr.create_and_render_video(
            topic=body.topic or None,
            style=body.style,
            aspect_ratio=body.aspect_ratio,
            language=body.language,
            targets=body.targets,
            instructions=body.instructions,
        )
    except Exception as e:
        raise _bad(e)


@app.delete("/api/videos/{video_id}")
def delete_video(video_id: int) -> dict[str, bool]:
    with session_scope() as s:
        v = s.get(VideoProject, video_id)
        if v:
            s.delete(v)
    return {"ok": True}


# ---------------------------------------------------------------- analytics & sentiment
@app.get("/api/analytics")
def get_analytics() -> dict[str, Any]:
    from app.analytics import monitor

    return monitor.dashboard_summary()


@app.post("/api/analytics/refresh")
async def refresh_analytics() -> dict[str, Any]:
    from app.analytics import monitor, sentiment

    try:
        new_comments = await sentiment.poll_all_comments()
        await monitor.collect_metrics()
        audit = await monitor.run_quality_audit() if runtime.llm else None
        return {"new_comments": new_comments, "audit": audit, "summary": monitor.dashboard_summary()}
    except Exception as e:
        raise _bad(e)


# ---------------------------------------------------------------- targetolog (ads)
class AdProposalIn(BaseModel):
    goal: str
    platform: str = "meta"
    daily_budget: float | None = None
    total_budget: float | None = None
    currency: str = "USD"
    extra_notes: str = ""


class BudgetChangeIn(BaseModel):
    daily_budget: float
    total_budget: float | None = None


@app.get("/api/ads")
def list_ads() -> list[dict[str, Any]]:
    from app.ads import strategist

    return strategist.list_campaigns()


@app.post("/api/ads/propose")
async def propose_ad(body: AdProposalIn) -> dict[str, Any]:
    from app.ads import strategist

    try:
        return await strategist.propose_campaign(
            goal=body.goal,
            platform=body.platform if body.platform in ("meta", "google") else "meta",  # type: ignore[arg-type]
            daily_budget=body.daily_budget,
            total_budget=body.total_budget,
            currency=body.currency,
            extra_notes=body.extra_notes,
        )
    except Exception as e:
        raise _bad(e)


@app.post("/api/ads/{campaign_id}/budget")
async def ad_budget(campaign_id: int, body: BudgetChangeIn) -> dict[str, Any]:
    from app.ads import strategist

    try:
        aid = await strategist.request_budget_change(campaign_id, body.daily_budget, body.total_budget)
        return {"approval_id": aid}
    except Exception as e:
        raise _bad(e)


@app.post("/api/ads/{campaign_id}/pause")
async def ad_pause(campaign_id: int) -> dict[str, Any]:
    from app.ads import strategist

    try:
        return await strategist.pause_campaign(campaign_id)
    except Exception as e:
        raise _bad(e)


@app.post("/api/ads/{campaign_id}/resume")
async def ad_resume(campaign_id: int) -> dict[str, Any]:
    from app.ads import strategist

    try:
        aid = await strategist.request_resume_campaign(campaign_id)
        return {"approval_id": aid}
    except Exception as e:
        raise _bad(e)


# ---------------------------------------------------------------- settings & activity
@app.get("/api/settings")
def read_settings() -> dict[str, Any]:
    return get_settings()


@app.put("/api/settings")
def write_settings(body: dict[str, Any]) -> dict[str, Any]:
    return save_settings(body)


@app.get("/api/activity")
def activity(limit: int = 200) -> list[dict[str, Any]]:
    with session_scope() as s:
        return [
            {"kind": a.kind, "level": a.level, "message": a.message, "created_at": a.created_at.isoformat() + "Z"}
            for a in s.query(Activity).order_by(Activity.id.desc()).limit(limit).all()
        ]


# ---------------------------------------------------------------- public media (for IG Reels & preview)
media_app = FastAPI(docs_url=None, redoc_url=None)


@media_app.get("/videos/{video_id}.mp4")
def serve_video(video_id: int) -> FileResponse:
    with session_scope() as s:
        v = s.get(VideoProject, video_id)
        path = Path(v.video_path) if v and v.video_path else None
    if not path or not path.exists():
        raise HTTPException(404, "Video topilmadi")
    return FileResponse(path, media_type="video/mp4")


@media_app.get("/thumbs/{video_id}.jpg")
def serve_thumb(video_id: int) -> FileResponse:
    with session_scope() as s:
        v = s.get(VideoProject, video_id)
        path = Path(v.thumbnail_path) if v and v.thumbnail_path else None
    if not path or not path.exists():
        raise HTTPException(404, "Thumbnail topilmadi")
    return FileResponse(path, media_type="image/jpeg")


app.mount("/media", media_app)


# ---------------------------------------------------------------- static UI
@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
