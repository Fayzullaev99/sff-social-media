"""AI Targetolog: designs ad campaigns, optimizes performance, and enforces human approval on EVERY spend."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.ads.clients import google_ads, meta_ads
from app.approvals import service as approvals
from app.content.posts import _random_knowledge
from app.core import runtime
from app.core.state import get_settings, log_activity
from app.db import AdCampaign, session_scope
from app.knowledge import store


class AdProposal(BaseModel):
    name: str = Field(description="Clear campaign name")
    objective: Literal["awareness", "traffic", "leads", "engagement", "sales"]
    age_min: int = Field(default=18)
    age_max: int = Field(default=45)
    gender: Literal["all", "male", "female"] = Field(default="all")
    locations: list[str] = Field(description="Target cities/regions, e.g. Tashkent, Samarkand, Uzbekistan")
    interests: list[str] = Field(description="5-10 precise targeting interests")
    languages: list[str] = Field(description="Target languages e.g. Uzbek, Russian")
    headline: str = Field(description="Short high-converting headline (max 45 chars)")
    primary_text: str = Field(description="Main ad copy in Uzbek (grounded in knowledge base)")
    call_to_action: str = Field(description="CTA button text e.g. Batafsil, Yozish, Buyurtma berish")
    creative_brief: str = Field(description="Visual/video creative direction")
    suggested_daily_budget: float = Field(description="Conservative daily budget in campaign currency")
    rationale_uz: str = Field(description="Why this targeting & budget makes sense (in Uzbek)")


def campaign_to_dict(c: AdCampaign) -> dict[str, Any]:
    return {
        "id": c.id,
        "platform": c.platform,
        "external_id": c.external_id,
        "name": c.name,
        "objective": c.objective,
        "target_audience": c.target_audience or {},
        "ad_copy": c.ad_copy or {},
        "daily_budget": c.daily_budget,
        "total_budget": c.total_budget,
        "currency": c.currency,
        "status": c.status,
        "approval_id": c.approval_id,
        "metrics": c.metrics or {},
        "ai_notes": c.ai_notes,
        "created_at": c.created_at.isoformat() + "Z" if c.created_at else None,
        "updated_at": c.updated_at.isoformat() + "Z" if c.updated_at else None,
    }


def list_campaigns(limit: int = 50) -> list[dict[str, Any]]:
    with session_scope() as s:
        return [campaign_to_dict(c) for c in s.query(AdCampaign).order_by(AdCampaign.id.desc()).limit(limit).all()]


def get_campaign(campaign_id: int) -> dict[str, Any] | None:
    with session_scope() as s:
        c = s.get(AdCampaign, campaign_id)
        return campaign_to_dict(c) if c else None


async def propose_campaign(
    *,
    goal: str,
    platform: Literal["meta", "google"] = "meta",
    daily_budget: float | None = None,
    total_budget: float | None = None,
    currency: str | None = None,
    extra_notes: str = "",
) -> dict[str, Any]:
    """AI Targetolog drafts a complete campaign and sends it to the human Approval queue (NEVER auto-spends)."""
    llm = runtime.require_llm()
    cfg = get_settings()
    acfg = cfg.get("ads", {})
    p = cfg.get("persona", {})

    currency = currency or acfg.get("default_currency", "USD")
    max_daily = float(acfg.get("max_suggested_daily_budget", 20.0))

    hits = await store.search(goal, k=5) if goal else []
    kb = [f"({h.doc_title}) {h.text}" for h in hits] or _random_knowledge(4)

    prompt = f"""You are a senior performance marketer (targetolog) for {p.get('owner_name', 'Admin')} ({p.get('role', '')}).
Design ONE high-ROI advertising campaign for platform: {platform.upper()}.
Business goal: {goal}
Currency: {currency}. Max suggested daily budget: {max_daily} {currency}.
{('Extra instructions: ' + extra_notes) if extra_notes else ''}

Rules:
- Ad copy facts (prices, offers, guarantees) MUST come strictly from KNOWLEDGE.
- Write headline, primary_text, call_to_action and rationale_uz in natural Uzbek.
- Be realistic and conservative with budget.

KNOWLEDGE:
{chr(10).join(kb) or '(empty — focus on brand awareness & consultation leads without inventing prices)'}"""

    prop = await llm.generate_json(prompt, AdProposal, temperature=0.6)
    final_daily = round(float(daily_budget if daily_budget is not None else min(prop.suggested_daily_budget, max_daily)), 2)
    final_daily = max(1.0, final_daily)
    final_total = round(float(total_budget if total_budget is not None else final_daily * 7), 2)

    audience = {
        "age_min": prop.age_min,
        "age_max": prop.age_max,
        "gender": prop.gender,
        "locations": prop.locations,
        "interests": prop.interests,
        "languages": prop.languages,
    }
    ad_copy = {
        "headline": prop.headline,
        "primary_text": prop.primary_text,
        "call_to_action": prop.call_to_action,
        "creative_brief": prop.creative_brief,
    }

    with session_scope() as s:
        c = AdCampaign(
            platform=platform,
            name=prop.name[:500],
            objective=prop.objective,
            target_audience=audience,
            ad_copy=ad_copy,
            daily_budget=final_daily,
            total_budget=final_total,
            currency=currency,
            status="pending_approval",
            ai_notes=prop.rationale_uz,
        )
        s.add(c)
        s.flush()
        cid = c.id

    # Mandatory money approval!
    approval_id = await approvals.request(
        "ad_campaign_launch",
        f"[{platform.upper()}] {prop.name} — kunlik {final_daily} {currency} (jami {final_total} {currency})",
        {
            "campaign_id": cid,
            "platform": platform,
            "name": prop.name,
            "objective": prop.objective,
            "daily_budget": final_daily,
            "total_budget": final_total,
            "currency": currency,
            "audience": audience,
            "ad_copy": ad_copy,
            "rationale": prop.rationale_uz,
        },
        amount=final_total,
        currency=currency,
    )
    with session_scope() as s:
        s.get(AdCampaign, cid).approval_id = approval_id

    log_activity("ads", f"🎯 Yangi reklama taklifi #{cid} ({prop.name}) — pul tasdig'i kutilmoqda")
    return get_campaign(cid)  # type: ignore[return-value]


async def request_budget_change(campaign_id: int, new_daily_budget: float, new_total_budget: float | None = None) -> int:
    c = get_campaign(campaign_id)
    if not c:
        raise KeyError(f"Kampaniya #{campaign_id} topilmadi")
    new_daily = max(1.0, round(float(new_daily_budget), 2))
    new_total = round(float(new_total_budget if new_total_budget is not None else new_daily * 7), 2)
    return await approvals.request(
        "ad_budget_change",
        f"[{c['platform'].upper()}] {c['name']}: byudjet {c['daily_budget']} → {new_daily} {c['currency']}/kun",
        {"campaign_id": campaign_id, "daily_budget": new_daily, "total_budget": new_total},
        amount=new_total,
        currency=c["currency"],
    )


async def request_resume_campaign(campaign_id: int) -> int:
    c = get_campaign(campaign_id)
    if not c:
        raise KeyError(f"Kampaniya #{campaign_id} topilmadi")
    return await approvals.request(
        "ad_campaign_resume",
        f"[{c['platform'].upper()}] {c['name']} ni qayta yoqish ({c['daily_budget']} {c['currency']}/kun)",
        {"campaign_id": campaign_id},
        amount=c["daily_budget"],
        currency=c["currency"],
    )


async def pause_campaign(campaign_id: int, reason: str = "Admin to'xtatdi") -> dict[str, Any]:
    """Pause an active campaign immediately (stops spending money — safe without money approval)."""
    c = get_campaign(campaign_id)
    if not c:
        raise KeyError(f"Kampaniya #{campaign_id} topilmadi")
    if c.get("external_id"):
        if c["platform"] == "meta" and meta_ads.configured:
            await meta_ads.pause_campaign(c["external_id"])
        elif c["platform"] == "google" and google_ads.configured:
            await google_ads.pause_campaign(c["external_id"])
    with session_scope() as s:
        row = s.get(AdCampaign, campaign_id)
        row.status = "paused"
        row.ai_notes = f"{row.ai_notes}\n[To'xtatildi]: {reason}".strip()
    log_activity("ads", f"⏸ Reklama #{campaign_id} to'xtatildi: {reason}")
    return get_campaign(campaign_id)  # type: ignore[return-value]


async def optimize_active_campaigns() -> int:
    """Refresh live metrics for active campaigns and pause clear money-losers (never increases spend without approval)."""
    checked = 0
    auto_pause = bool(get_settings().get("ads", {}).get("pause_underperforming_auto", True))
    with session_scope() as s:
        active = [campaign_to_dict(c) for c in s.query(AdCampaign).filter(AdCampaign.status == "active").all()]
    for c in active:
        if not c.get("external_id") or c["platform"] != "meta" or not meta_ads.configured:
            continue
        try:
            m = await meta_ads.fetch_insights(c["external_id"])
            if not m:
                continue
            checked += 1
            with session_scope() as s:
                s.get(AdCampaign, c["id"]).metrics = m
            # Protect budget: if >1000 impressions and CTR < 0.3%, pause to save money!
            if auto_pause and m.get("impressions", 0) >= 1000 and m.get("ctr", 1.0) < 0.3:
                await pause_campaign(c["id"], f"Past CTR ({m['ctr']:.2f}%), byudjetni tejash uchun to'xtatildi")
                if runtime.admin_bot:
                    await runtime.admin_bot.send_admins(
                        f"🛡 <b>Targetolog byudjetni himoya qildi</b>\n"
                        f"«{c['name']}» kampaniyasida CTR juda past ({m['ctr']:.2f}%), shuning uchun avtomatik to'xtatildi."
                    )
        except Exception as e:
            log_activity("ads", f"Kampaniya #{c['id']} metrikasini olishda xato: {e}", "warning")
    return checked


# ---------------------------------------------------------------- approval handlers
@approvals.on_approve("ad_campaign_launch")
async def _on_launch_approved(payload: dict[str, Any], approval_id: int) -> str:
    cid = int(payload["campaign_id"])
    c = get_campaign(cid)
    if not c:
        raise KeyError(f"Kampaniya #{cid} topilmadi")
    client = meta_ads if c["platform"] == "meta" else google_ads
    if not client.configured:
        with session_scope() as s:
            row = s.get(AdCampaign, cid)
            row.status = "paused"
            row.ai_notes = f"{row.ai_notes}\n[Tasdiqlandi, lekin {c['platform'].upper()} Ads API kalitlari .env da yo'q]".strip()
        return f"Tasdiqlandi (lekin {c['platform'].upper()} Ads API kalitlari .env ga kiritilmagan — qo'lda ishga tushirish mumkin)"
    ext_id = await client.launch_campaign(c, approval_id=approval_id)
    with session_scope() as s:
        row = s.get(AdCampaign, cid)
        row.external_id = ext_id
        row.status = "active"
    return f"Ishga tushirildi ({c['platform']} id: {ext_id})"


@approvals.on_reject("ad_campaign_launch")
async def _on_launch_rejected(payload: dict[str, Any], approval_id: int) -> str:
    with session_scope() as s:
        c = s.get(AdCampaign, int(payload["campaign_id"]))
        if c:
            c.status = "rejected"
    return "Kampaniya rad etildi"


@approvals.on_approve("ad_budget_change")
async def _on_budget_approved(payload: dict[str, Any], approval_id: int) -> str:
    cid = int(payload["campaign_id"])
    new_daily = float(payload["daily_budget"])
    new_total = float(payload.get("total_budget", new_daily * 7))
    c = get_campaign(cid)
    if not c:
        raise KeyError(f"Kampaniya #{cid} topilmadi")
    if c.get("external_id") and c["platform"] == "meta" and meta_ads.configured:
        await meta_ads.update_budget(c["external_id"], new_daily, approval_id=approval_id)
    with session_scope() as s:
        row = s.get(AdCampaign, cid)
        row.daily_budget = new_daily
        row.total_budget = new_total
    return f"Byudjet yangilandi: {new_daily} {c['currency']}/kun"


@approvals.on_approve("ad_campaign_resume")
async def _on_resume_approved(payload: dict[str, Any], approval_id: int) -> str:
    cid = int(payload["campaign_id"])
    c = get_campaign(cid)
    if not c:
        raise KeyError(f"Kampaniya #{cid} topilmadi")
    if c.get("external_id") and c["platform"] == "meta" and meta_ads.configured:
        await meta_ads.resume_campaign(c["external_id"], approval_id=approval_id)
    with session_scope() as s:
        s.get(AdCampaign, cid).status = "active"
    return "Kampaniya qayta yoqildi"
