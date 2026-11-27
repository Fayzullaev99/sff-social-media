"""Meta Marketing API & Google Ads API clients with defense-in-depth human approval checks."""
from __future__ import annotations

from typing import Any

import httpx

from app.config import env
from app.core.policy import MoneyActionBlocked
from app.core.state import log_activity
from app.db import Approval, session_scope

META_GRAPH = "https://graph.facebook.com/v21.0"

META_OBJECTIVE_MAP = {
    "awareness": "OUTCOME_AWARENESS",
    "traffic": "OUTCOME_TRAFFIC",
    "leads": "OUTCOME_LEADS",
    "engagement": "OUTCOME_ENGAGEMENT",
    "sales": "OUTCOME_SALES",
}


def verify_human_approval(approval_id: int | None) -> None:
    """Hard code-level money guard: no paid ad API call can run without a recorded human Approval."""
    if not approval_id:
        raise MoneyActionBlocked("Pul sarflaydigan reklama amali inson tasdig'isiz bajarilmaydi")
    with session_scope() as s:
        a = s.get(Approval, approval_id)
        if a is None or a.status not in ("approved", "executed") or not a.decided_by:
            raise MoneyActionBlocked(f"Approval #{approval_id} tasdiqlanmagan — reklama amali bloklandi")


class MetaAdsClient:
    @property
    def configured(self) -> bool:
        return env.meta_ads_configured

    def _account_path(self) -> str:
        acc = env.meta_ad_account_id
        return acc if acc.startswith("act_") else f"act_{acc}"

    async def launch_campaign(self, campaign: dict[str, Any], *, approval_id: int) -> str:
        verify_human_approval(approval_id)
        if not self.configured:
            raise RuntimeError("Meta Ads sozlanmagan (.env: META_ADS_ACCESS_TOKEN, META_AD_ACCOUNT_ID)")
        obj = META_OBJECTIVE_MAP.get(campaign.get("objective", "traffic"), "OUTCOME_TRAFFIC")
        daily_cents = max(100, int(round(float(campaign.get("daily_budget", 5.0)) * 100)))
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{META_GRAPH}/{self._account_path()}/campaigns",
                data={
                    "access_token": env.meta_ads_access_token,
                    "name": campaign["name"][:250],
                    "objective": obj,
                    "status": "ACTIVE",
                    "special_ad_categories": "[]",
                    "daily_budget": str(daily_cents),
                },
            )
            r.raise_for_status()
            ext_id = r.json()["id"]
        log_activity("ads", f"🚀 Meta Ads kampaniyasi ishga tushdi: {campaign['name']} (id={ext_id})")
        return ext_id

    async def update_budget(self, external_id: str, daily_budget: float, *, approval_id: int) -> None:
        verify_human_approval(approval_id)
        if not self.configured:
            raise RuntimeError("Meta Ads sozlanmagan")
        daily_cents = max(100, int(round(daily_budget * 100)))
        async with httpx.AsyncClient(timeout=25) as client:
            r = await client.post(
                f"{META_GRAPH}/{external_id}",
                data={"access_token": env.meta_ads_access_token, "daily_budget": str(daily_cents)},
            )
            r.raise_for_status()

    async def resume_campaign(self, external_id: str, *, approval_id: int) -> None:
        verify_human_approval(approval_id)
        if not self.configured:
            raise RuntimeError("Meta Ads sozlanmagan")
        async with httpx.AsyncClient(timeout=25) as client:
            r = await client.post(
                f"{META_GRAPH}/{external_id}",
                data={"access_token": env.meta_ads_access_token, "status": "ACTIVE"},
            )
            r.raise_for_status()

    async def pause_campaign(self, external_id: str) -> None:
        """Pausing stops spend — safe without money approval."""
        if not self.configured or not external_id:
            return
        async with httpx.AsyncClient(timeout=25) as client:
            r = await client.post(
                f"{META_GRAPH}/{external_id}",
                data={"access_token": env.meta_ads_access_token, "status": "PAUSED"},
            )
            r.raise_for_status()

    async def fetch_insights(self, external_id: str) -> dict[str, Any]:
        if not self.configured or not external_id:
            return {}
        async with httpx.AsyncClient(timeout=25) as client:
            r = await client.get(
                f"{META_GRAPH}/{external_id}/insights",
                params={
                    "access_token": env.meta_ads_access_token,
                    "fields": "impressions,clicks,spend,ctr,cpc,reach",
                    "date_preset": "last_7d",
                },
            )
            r.raise_for_status()
            rows = r.json().get("data", [])
            if not rows:
                return {}
            d = rows[0]
            return {
                "impressions": int(d.get("impressions", 0)),
                "clicks": int(d.get("clicks", 0)),
                "spend": float(d.get("spend", 0.0)),
                "ctr": float(d.get("ctr", 0.0)),
                "cpc": float(d.get("cpc", 0.0)),
                "reach": int(d.get("reach", 0)),
            }


class GoogleAdsClient:
    @property
    def configured(self) -> bool:
        return env.google_ads_configured

    async def _access_token(self) -> str:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": env.google_ads_client_id,
                    "client_secret": env.google_ads_client_secret,
                    "refresh_token": env.google_ads_refresh_token,
                    "grant_type": "refresh_token",
                },
            )
            r.raise_for_status()
            return r.json()["access_token"]

    async def launch_campaign(self, campaign: dict[str, Any], *, approval_id: int) -> str:
        verify_human_approval(approval_id)
        if not self.configured:
            raise RuntimeError("Google Ads sozlanmagan (.env: GOOGLE_ADS_*)")
        token = await self._access_token()
        cid = env.google_ads_customer_id.replace("-", "")
        headers = {
            "Authorization": f"Bearer {token}",
            "developer-token": env.google_ads_developer_token,
            "Content-Type": "application/json",
        }
        micros = max(1_000_000, int(round(float(campaign.get("daily_budget", 5.0)) * 1_000_000)))
        async with httpx.AsyncClient(timeout=30) as client:
            # 1. Create budget
            b_res = await client.post(
                f"https://googleads.googleapis.com/v18/customers/{cid}/campaignBudgets:mutate",
                headers=headers,
                json={"operations": [{"create": {"name": f"{campaign['name']} budget", "amountMicros": str(micros), "deliveryMethod": "STANDARD"}}]},
            )
            b_res.raise_for_status()
            budget_rn = b_res.json()["results"][0]["resourceName"]
            # 2. Create campaign
            c_res = await client.post(
                f"https://googleads.googleapis.com/v18/customers/{cid}/campaigns:mutate",
                headers=headers,
                json={
                    "operations": [{
                        "create": {
                            "name": campaign["name"][:250],
                            "advertisingChannelType": "SEARCH",
                            "status": "ENABLED",
                            "campaignBudget": budget_rn,
                        }
                    }]
                },
            )
            c_res.raise_for_status()
            ext_id = c_res.json()["results"][0]["resourceName"]
        log_activity("ads", f"🚀 Google Ads kampaniyasi ishga tushdi: {campaign['name']} ({ext_id})")
        return ext_id

    async def pause_campaign(self, external_id: str) -> None:
        if not self.configured or not external_id:
            return
        token = await self._access_token()
        cid = env.google_ads_customer_id.replace("-", "")
        async with httpx.AsyncClient(timeout=25) as client:
            r = await client.post(
                f"https://googleads.googleapis.com/v18/customers/{cid}/campaigns:mutate",
                headers={"Authorization": f"Bearer {token}", "developer-token": env.google_ads_developer_token},
                json={"operations": [{"update": {"resourceName": external_id, "status": "PAUSED"}, "updateMask": "status"}]},
            )
            r.raise_for_status()


meta_ads = MetaAdsClient()
google_ads = GoogleAdsClient()
