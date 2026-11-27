import asyncio
from datetime import datetime

import numpy as np
import pytest

from app.approvals import service as approvals
from app.channels.telegram_userbot import split_text
from app.core.policy import MoneyActionBlocked, RateLimiter, is_money_kind, within_working_hours
from app.knowledge.store import VectorIndex, chunk_text


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------- knowledge
def test_chunking_respects_size_and_keeps_text():
    text = "\n\n".join(f"Paragraf {i}. " + "so'z " * 60 for i in range(20))
    chunks = chunk_text(text, size=500, overlap=80)
    assert len(chunks) > 3
    assert all(len(c) <= 500 for c in chunks)
    assert "Paragraf 0." in chunks[0] and "Paragraf 19." in chunks[-1]


def test_chunking_long_paragraph_is_split():
    chunks = chunk_text("a" * 2500, size=1000, overlap=100)
    assert len(chunks) == 3 and all(len(c) <= 1000 for c in chunks)


def test_chunking_empty():
    assert chunk_text("   \n\n ") == []


def test_vector_search_orders_by_similarity():
    idx = VectorIndex()
    idx._matrix = np.array([[1, 0, 0], [0, 1, 0], [0.7, 0.7, 0]], dtype=np.float32)
    idx._meta = [("A", 1, "a"), ("B", 2, "b"), ("C", 3, "c")]
    idx._dirty = False
    hits = idx.search_vector(np.array([1, 0, 0], dtype=np.float32), k=2)
    assert [h.text for h in hits] == ["A", "C"]


# ---------------------------------------------------------------- policy
def test_rate_limiter_cooldown_and_global_cap():
    rl = RateLimiter()
    assert rl.allow(1, now=100.0)
    rl.record(1, now=100.0)
    assert not rl.allow(1, now=101.0)  # per-chat cooldown (3s default)
    assert rl.allow(1, now=104.0)
    for i in range(20):
        rl.record(1000 + i, now=200.0)
    assert not rl.allow(5, now=201.0)  # global cap 20/min
    assert rl.allow(5, now=261.0)


@pytest.mark.parametrize(
    "spec,hour,expected",
    [("", 3, True), ("08:00-23:00", 9, True), ("08:00-23:00", 23, False), ("20:00-02:00", 1, True), ("20:00-02:00", 12, False)],
)
def test_working_hours(spec, hour, expected):
    assert within_working_hours(datetime(2026, 1, 1, hour, 30), spec) is expected


def test_split_text():
    parts = split_text("x" * 9000, limit=4000)
    assert len(parts) == 3 and all(len(p) <= 4000 for p in parts)


# ---------------------------------------------------------------- money guard
def test_money_kind_is_flagged_and_never_runs_without_human():
    calls = []

    @approvals.on_approve("ad_campaign_launch")
    async def _launch(payload, approval_id):
        calls.append(payload)
        return "launched"

    assert is_money_kind("ad_campaign_launch")
    aid = run(approvals.request("ad_campaign_launch", "Test kampaniya", {"budget": 50}, amount=50, currency="USD"))
    a = approvals.get(aid)
    assert a["requires_money"] and a["status"] == "pending"

    # Direct execution without a recorded human decision must be blocked
    with pytest.raises(MoneyActionBlocked):
        run(approvals._execute(aid))
    # Decision without identity is refused
    with pytest.raises(MoneyActionBlocked):
        run(approvals.decide(aid, True, decided_by=""))
    assert calls == []

    result = run(approvals.decide(aid, True, decided_by="web:admin"))
    assert result["status"] == "executed" and calls == [{"budget": 50}]

    # Already decided -> cannot run again
    run(approvals.decide(aid, True, decided_by="web:admin"))
    assert len(calls) == 1


def test_rejected_action_does_not_execute():
    calls = []

    @approvals.on_approve("paid_service")
    async def _pay(payload, approval_id):
        calls.append(1)
        return "paid"

    aid = run(approvals.request("paid_service", "Xizmat", {}))
    result = run(approvals.decide(aid, False, decided_by="tg:1"))
    assert result["status"] == "rejected" and calls == []


def test_any_amount_marks_money():
    aid = run(approvals.request("publish_post", "Pullik post", {"post_id": 0}, amount=10))
    assert approvals.get(aid)["requires_money"]
