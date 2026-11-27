"""Tests for Phase 3 (Video Factory, YouTube/Instagram) and Phase 4 (Analytics, Sentiment, Targetolog)."""
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.ads import strategist
from app.ads.clients import MetaAdsClient, verify_human_approval
from app.analytics import monitor, sentiment
from app.approvals import service as approvals
from app.content.video import render as video_render
from app.core import runtime
from app.core.brain import AgentDecision, BrainResult
from app.core.policy import MoneyActionBlocked
from app.core.state import get_settings


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------- Video Factory (real FFmpeg render!)
def test_video_factory_renders_real_mp4_and_queues_approval():
    scenes = [
        {"narration": "Salom! Bu sinov videosi.", "on_screen_text": "Sinov 1-sahna", "visual_query": "office", "duration_sec": 1.5},
        {"narration": "Obuna bo'ling va izoh qoldiring!", "on_screen_text": "Obuna bo'ling!", "visual_query": "city", "duration_sec": 1.5},
    ]
    v = run(
        video_render.create_and_render_video(
            topic="Test Short",
            style="kinetic",
            aspect_ratio="9:16",
            language="uz",
            targets=[],
            scenes_override=scenes,
            title_override="Test Video",
            silent_audio=True,
        )
    )
    assert v["status"] == "pending"
    assert v["approval_id"] is not None
    assert v["duration_sec"] >= 2.0
    mp4 = Path(v["video_path"])
    assert mp4.exists() and mp4.stat().st_size > 10_000
    assert Path(v["subtitle_path"]).exists()
    assert "Sinov" in v["scenes"][0]["on_screen_text"]

    # Rejecting approval marks video as rejected
    res = run(approvals.decide(v["approval_id"], False, decided_by="web:admin"))
    assert res["status"] == "rejected"
    assert video_render.get_video(v["id"])["status"] == "rejected"


# ---------------------------------------------------------------- Targetolog & Hard Money Guard
def test_meta_ads_client_blocks_without_human_approval():
    client = MetaAdsClient()
    with pytest.raises(MoneyActionBlocked):
        verify_human_approval(None)
    with pytest.raises(MoneyActionBlocked):
        run(client.launch_campaign({"name": "Hack", "daily_budget": 100}, approval_id=0))

    # Pending approval is ALSO blocked until human approves!
    aid = run(approvals.request("ad_campaign_launch", "Pending ad", {"campaign_id": 999}, amount=50, currency="USD"))
    with pytest.raises(MoneyActionBlocked):
        verify_human_approval(aid)


def test_targetolog_propose_requires_money_approval_and_executes_only_after_human(monkeypatch):
    fake_llm = MagicMock()
    fake_llm.generate_json = AsyncMock(
        return_value=strategist.AdProposal(
            name="Toshkent Leads Q4",
            objective="leads",
            age_min=20,
            age_max=40,
            gender="all",
            locations=["Tashkent"],
            interests=["Business", "Marketing"],
            languages=["Uzbek", "Russian"],
            headline="Sifatli xizmat!",
            primary_text="Hoziroq murojaat qiling.",
            call_to_action="Yozish",
            creative_brief="Vertical video with product demo",
            suggested_daily_budget=10.0,
            rationale_uz="Toshkent auditoriyasi eng yuqori konversiyaga ega",
        )
    )
    monkeypatch.setattr(runtime, "llm", fake_llm)

    camp = run(strategist.propose_campaign(goal="Toshkentdan mijoz topish", platform="meta", daily_budget=8.0, total_budget=56.0))
    assert camp["status"] == "pending_approval"
    assert camp["approval_id"] is not None

    ap = approvals.get(camp["approval_id"])
    assert ap["requires_money"] is True
    assert ap["amount"] == 56.0
    assert ap["status"] == "pending"

    # Budget change also creates a money approval
    bud_aid = run(strategist.request_budget_change(camp["id"], 15.0))
    bud_ap = approvals.get(bud_aid)
    assert bud_ap["requires_money"] is True and bud_ap["kind"] == "ad_budget_change"

    # Rejecting launch marks campaign rejected
    run(approvals.decide(camp["approval_id"], False, decided_by="tg:1"))
    assert strategist.get_campaign(camp["id"])["status"] == "rejected"


# ---------------------------------------------------------------- Analytics, Sentiment & Self-Correction
def test_comment_sentiment_spam_and_multilingual_reply(monkeypatch):
    # 1. Spam comment -> moderated
    monkeypatch.setattr(
        sentiment,
        "analyze_sentiment",
        AsyncMock(return_value=sentiment.SentimentResult(
            sentiment="spam", score=-0.9, language="en", is_complaint=False, summary="Spam link"
        )),
    )
    fake_yt = MagicMock(configured=True)
    fake_yt.moderate_comment = AsyncMock()
    fake_yt.reply_comment = AsyncMock()
    monkeypatch.setattr(runtime, "youtube", fake_yt)

    c1 = run(sentiment.handle_comment("youtube", {"external_id": "yt_spam_1", "author": "Bot", "text": "FREE CRYPTO CLICK HERE"}))
    assert c1["status"] == "moderated"
    fake_yt.moderate_comment.assert_awaited_once_with("yt_spam_1", reject=True)

    # 2. Russian positive comment -> replied in Russian
    monkeypatch.setattr(
        sentiment,
        "analyze_sentiment",
        AsyncMock(return_value=sentiment.SentimentResult(
            sentiment="positive", score=0.9, language="ru", is_complaint=False, summary="Ijobiy izoh"
        )),
    )
    from app.core import brain

    monkeypatch.setattr(
        brain,
        "decide_reply",
        AsyncMock(return_value=BrainResult(
            decision=AgentDecision(
                should_reply=True, reply="Спасибо большое за отзыв!", language="ru", confidence=0.95, needs_admin=False, reason="Ijobiy"
            ),
            escalate=False,
        )),
    )
    c2 = run(sentiment.handle_comment("youtube", {"external_id": "yt_ok_2", "author": "Ivan", "text": "Отличное видео!"}))
    assert c2["status"] == "replied" and c2["language"] == "ru"
    fake_yt.reply_comment.assert_awaited_once_with("yt_ok_2", "Спасибо большое за отзыв!")


def test_quality_audit_applies_self_correction(monkeypatch):
    fake_llm = MagicMock()
    fake_llm.generate_json = AsyncMock(
        return_value=monitor.QualityAudit(
            quality_rating=8.4,
            summary_uz="Obunachilar video tezligini maqtashdi, narx haqida ko'proq ma'lumot so'rashdi.",
            issues_uz=["Videolarda narx diapazoni kam aytilgan"],
            self_correction_guidance="Har bir video oxirida xizmat shartlari va narxga havola qo'shing.",
            severity="info",
            notify_admin=False,
        )
    )
    monkeypatch.setattr(runtime, "llm", fake_llm)

    res = run(monitor.run_quality_audit())
    assert res["quality_rating"] == 8.4
    assert "narxga havola" in get_settings()["content"]["learned_guidance"]
    summary = monitor.dashboard_summary()
    assert summary["quality_rating"] == 8.4
    assert len(summary["insights"]) >= 1
