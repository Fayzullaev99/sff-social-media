"""Official Instagram Graph API channel: Reels, image posts, comments, moderation & insights.

Requires an Instagram Business or Creator account linked to a Facebook Page,
plus IG_ACCESS_TOKEN and IG_ACCOUNT_ID in .env.
"""
from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.config import env
from app.core.state import log_activity

GRAPH = "https://graph.facebook.com/v21.0"


class InstagramChannel:
    def __init__(self) -> None:
        self.username: str | None = None

    @property
    def configured(self) -> bool:
        return env.instagram_configured

    def _params(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        p: dict[str, Any] = {"access_token": env.ig_access_token}
        if extra:
            p.update(extra)
        return p

    async def verify(self) -> str | None:
        if not self.configured:
            return None
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(
                f"{GRAPH}/{env.ig_account_id}",
                params=self._params({"fields": "username,followers_count,media_count"}),
            )
            r.raise_for_status()
            data = r.json()
            self.username = data.get("username")
            if self.username:
                log_activity("instagram", f"Instagram ulandi: @{self.username}")
            return self.username

    async def publish_reel(self, *, video_id: int, caption: str, video_url: str | None = None) -> str:
        """Publish an Instagram Reel via the official 2-step Graph API container flow."""
        if not self.configured:
            raise RuntimeError("Instagram sozlanmagan (.env: IG_ACCESS_TOKEN, IG_ACCOUNT_ID)")
        url = video_url or (f"{env.public_media_base_url}/media/videos/{video_id}.mp4" if env.public_media_base_url else "")
        if not url or not url.startswith("https://"):
            raise RuntimeError(
                "Instagram Graph API video uchun tashqi HTTPS havola talab qiladi. "
                ".env faylida PUBLIC_MEDIA_BASE_URL ni kiriting (masalan VPS domeningiz yoki ngrok HTTPS URL)."
            )

        async with httpx.AsyncClient(timeout=60) as client:
            # Step 1: Create REELS media container
            r = await client.post(
                f"{GRAPH}/{env.ig_account_id}/media",
                params=self._params({"media_type": "REELS", "video_url": url, "caption": caption[:2200]}),
            )
            r.raise_for_status()
            creation_id = r.json()["id"]

            # Step 2: Poll container status until FINISHED
            for _ in range(30):
                await asyncio.sleep(5)
                st = await client.get(
                    f"{GRAPH}/{creation_id}", params=self._params({"fields": "status_code,status"})
                )
                code = st.json().get("status_code")
                if code == "FINISHED":
                    break
                if code == "ERROR":
                    raise RuntimeError(f"Instagram video qayta ishlashda xato: {st.json()}")
            else:
                raise RuntimeError("Instagram konteyner vaqti tugadi")

            # Step 3: Publish container
            pub = await client.post(
                f"{GRAPH}/{env.ig_account_id}/media_publish",
                params=self._params({"creation_id": creation_id}),
            )
            pub.raise_for_status()
            media_id = pub.json()["id"]

            # Fetch permalink if available
            link = f"https://instagram.com/p/{media_id}"
            try:
                p_res = await client.get(f"{GRAPH}/{media_id}", params=self._params({"fields": "permalink"}))
                link = p_res.json().get("permalink", link)
            except Exception:
                pass
            log_activity("instagram", f"📸 Instagram Reel joylandi: {link}")
            return link

    async def fetch_recent_comments(self, limit: int = 30) -> list[dict[str, Any]]:
        if not self.configured:
            return []
        out: list[dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=25) as client:
            media = await client.get(
                f"{GRAPH}/{env.ig_account_id}/media",
                params=self._params({"fields": "id,caption", "limit": 8}),
            )
            media.raise_for_status()
            for m in media.json().get("data", []):
                cm = await client.get(
                    f"{GRAPH}/{m['id']}/comments",
                    params=self._params({"fields": "id,text,username,timestamp,replies{id}", "limit": 15}),
                )
                if cm.status_code != 200:
                    continue
                for c in cm.json().get("data", []):
                    if self.username and c.get("username") == self.username:
                        continue
                    if (c.get("replies") or {}).get("data"):
                        continue
                    out.append({
                        "external_id": c["id"],
                        "post_external_id": m["id"],
                        "author": c.get("username", "user"),
                        "text": c.get("text", ""),
                    })
                    if len(out) >= limit:
                        return out
        return out

    async def reply_comment(self, comment_id: str, text: str) -> str:
        async with httpx.AsyncClient(timeout=25) as client:
            r = await client.post(
                f"{GRAPH}/{comment_id}/replies",
                params=self._params({"message": text[:1000]}),
            )
            r.raise_for_status()
            rid = r.json().get("id", "")
        log_activity("instagram", f"💬 Instagram izohiga javob berildi ({comment_id})")
        return rid

    async def hide_comment(self, comment_id: str) -> None:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(f"{GRAPH}/{comment_id}", params=self._params({"hide": "true"}))
            r.raise_for_status()
        log_activity("instagram", f"🛡 Instagram spam izohi yashirildi ({comment_id})")

    async def fetch_account_stats(self) -> dict[str, Any] | None:
        if not self.configured:
            return None
        async with httpx.AsyncClient(timeout=25) as client:
            r = await client.get(
                f"{GRAPH}/{env.ig_account_id}",
                params=self._params({"fields": "username,followers_count,media_count"}),
            )
            r.raise_for_status()
            acc = r.json()
            media = await client.get(
                f"{GRAPH}/{env.ig_account_id}/media",
                params=self._params({"fields": "id,caption,like_count,comments_count,media_type", "limit": 10}),
            )
            posts = media.json().get("data", []) if media.status_code == 200 else []
            likes = sum(int(p.get("like_count", 0)) for p in posts)
            comments = sum(int(p.get("comments_count", 0)) for p in posts)
            return {
                "title": f"@{acc.get('username', '')}",
                "followers": int(acc.get("followers_count", 0)),
                "media_count": int(acc.get("media_count", 0)),
                "likes": likes,
                "comments": comments,
                "recent_posts": posts,
            }
