"""Database engine, ORM models and small helpers."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    create_engine,
    event,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from app.config import env


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


engine = create_engine(
    env.database_url,
    connect_args={"check_same_thread": False} if env.database_url.startswith("sqlite") else {},
    future=True,
)

if env.database_url.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _):  # pragma: no cover - trivial
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()


SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)


class Base(DeclarativeBase):
    pass


class Chat(Base):
    """A Telegram dialog known to the agent. Only `allowed` chats get automatic replies."""

    __tablename__ = "chats"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # Telegram marked peer id
    title: Mapped[str] = mapped_column(String(255), default="")
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    kind: Mapped[str] = mapped_column(String(20), default="user")  # user|group|channel|discussion
    allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    mode: Mapped[str] = mapped_column(String(20), default="auto")  # auto|approve
    linked_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    tg_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sender_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sender_name: Mapped[str] = mapped_column(String(255), default="")
    direction: Mapped[str] = mapped_column(String(10))  # in|out|owner
    text: Mapped[str] = mapped_column(Text, default="")
    language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class KnowledgeDoc(Base):
    __tablename__ = "knowledge_docs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(500))
    source: Mapped[str] = mapped_column(String(1000), default="")
    kind: Mapped[str] = mapped_column(String(30), default="text")  # file|text|url|admin_answer
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    char_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    doc_id: Mapped[int] = mapped_column(ForeignKey("knowledge_docs.id", ondelete="CASCADE"), index=True)
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[bytes] = mapped_column(LargeBinary)


class Escalation(Base):
    """A question the agent could not answer from its knowledge base."""

    __tablename__ = "escalations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger)
    chat_title: Mapped[str] = mapped_column(String(255), default="")
    tg_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sender_name: Mapped[str] = mapped_column(String(255), default="")
    question: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(10), default="uz")
    reason: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="open")  # open|answered|dismissed
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Approval(Base):
    """Any action that needs a human decision. Money actions ALWAYS go through here."""

    __tablename__ = "approvals"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(50), index=True)
    title: Mapped[str] = mapped_column(String(500), default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    requires_money: Mapped[bool] = mapped_column(Boolean, default=False)
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    # pending|approved|rejected|executed|failed
    decided_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Post(Base):
    __tablename__ = "posts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    platform: Mapped[str] = mapped_column(String(20), default="telegram")
    channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    channel_title: Mapped[str] = mapped_column(String(255), default="")
    topic: Mapped[str] = mapped_column(String(500), default="")
    text: Mapped[str] = mapped_column(Text, default="")
    media_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    # pending|scheduled|published|rejected|failed
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    approval_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)


class Activity(Base):
    __tablename__ = "activity"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(50))
    level: Mapped[str] = mapped_column(String(10), default="info")
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class VideoProject(Base):
    """Generated video for YouTube Shorts/Videos, Instagram Reels, or Telegram."""

    __tablename__ = "video_projects"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    topic: Mapped[str] = mapped_column(String(500), default="")
    style: Mapped[str] = mapped_column(String(30), default="stock")  # stock|kinetic|ai_veo|avatar
    aspect_ratio: Mapped[str] = mapped_column(String(10), default="9:16")  # 9:16|16:9
    language: Mapped[str] = mapped_column(String(10), default="uz")
    title: Mapped[str] = mapped_column(String(500), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    script: Mapped[str] = mapped_column(Text, default="")
    scenes: Mapped[list] = mapped_column(JSON, default=list)
    voice: Mapped[str] = mapped_column(String(100), default="")
    audio_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    subtitle_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    video_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    thumbnail_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    duration_sec: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(30), default="draft")
    # draft|rendering|ready|pending|published|rejected|failed
    targets: Mapped[list] = mapped_column(JSON, default=list)  # ["youtube", "instagram", "telegram"]
    published_urls: Mapped[dict] = mapped_column(JSON, default=dict)
    approval_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class SocialComment(Base):
    """Comments from YouTube, Instagram, or Telegram with sentiment & reply tracking."""

    __tablename__ = "social_comments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    platform: Mapped[str] = mapped_column(String(20), index=True)  # youtube|instagram|telegram
    external_id: Mapped[str] = mapped_column(String(200), index=True)
    post_external_id: Mapped[str] = mapped_column(String(200), default="")
    author: Mapped[str] = mapped_column(String(255), default="")
    text: Mapped[str] = mapped_column(Text, default="")
    language: Mapped[str] = mapped_column(String(10), default="uz")
    sentiment: Mapped[str] = mapped_column(String(20), default="neutral")  # positive|neutral|negative|spam
    sentiment_score: Mapped[float] = mapped_column(Float, default=0.0)  # -1.0 .. 1.0
    reply_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="new")  # new|replied|moderated|escalated|ignored
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    replied_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class MetricSnapshot(Base):
    """Periodic metrics across Telegram, YouTube, and Instagram."""

    __tablename__ = "metric_snapshots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    platform: Mapped[str] = mapped_column(String(20), index=True)
    external_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    title: Mapped[str] = mapped_column(String(500), default="")
    followers: Mapped[int] = mapped_column(Integer, default=0)
    views: Mapped[int] = mapped_column(Integer, default=0)
    likes: Mapped[int] = mapped_column(Integer, default=0)
    comments_count: Mapped[int] = mapped_column(Integer, default=0)
    shares: Mapped[int] = mapped_column(Integer, default=0)
    engagement_rate: Mapped[float] = mapped_column(Float, default=0.0)
    avg_sentiment: Mapped[float] = mapped_column(Float, default=0.0)
    raw: Mapped[dict] = mapped_column(JSON, default=dict)
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class FeedbackInsight(Base):
    """Audience feedback analysis, quality rating alerts, and self-correction actions."""

    __tablename__ = "feedback_insights"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    platform: Mapped[str] = mapped_column(String(20), default="all")
    category: Mapped[str] = mapped_column(String(40), default="quality")  # quality|sentiment|strategy|correction
    severity: Mapped[str] = mapped_column(String(20), default="info")  # info|warning|critical
    summary: Mapped[str] = mapped_column(Text)
    action_taken: Mapped[str] = mapped_column(Text, default="")
    auto_applied: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class AdCampaign(Base):
    """Advertising campaigns managed by the Targetolog module. Money spends ALWAYS require Approval."""

    __tablename__ = "ad_campaigns"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    platform: Mapped[str] = mapped_column(String(20), default="meta")  # meta|google
    external_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    name: Mapped[str] = mapped_column(String(500), default="")
    objective: Mapped[str] = mapped_column(String(40), default="traffic")  # awareness|traffic|leads|engagement|sales
    target_audience: Mapped[dict] = mapped_column(JSON, default=dict)
    ad_copy: Mapped[dict] = mapped_column(JSON, default=dict)
    daily_budget: Mapped[float] = mapped_column(Float, default=5.0)
    total_budget: Mapped[float] = mapped_column(Float, default=50.0)
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    status: Mapped[str] = mapped_column(String(30), default="proposal")
    # proposal|pending_approval|active|paused|rejected|completed|failed
    approval_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    ai_notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


def init_db() -> None:
    Base.metadata.create_all(engine)


@contextmanager
def session_scope() -> Iterator[Any]:
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()
