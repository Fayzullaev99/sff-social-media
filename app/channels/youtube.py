"""YouTube Data API v3 channel integration: uploads, comments, moderation, metadata updates & stats."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from app.config import env
from app.core.state import log_activity

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/youtube.readonly",
]


class YouTubeChannel:
    def __init__(self) -> None:
        self._service: Any = None
        self.channel_title: str | None = None

    @property
    def configured(self) -> bool:
        return env.yt_token_path.exists()

    def _build_service(self) -> Any:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        if not env.yt_token_path.exists():
            raise RuntimeError("YouTube token topilmadi. Avval bir marta: .venv\\Scripts\\python youtube_auth.py")

        creds = Credentials.from_authorized_user_file(str(env.yt_token_path), SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            env.yt_token_path.write_text(creds.to_json(), encoding="utf-8")
        self._service = build("youtube", "v3", credentials=creds, cache_discovery=False)
        return self._service

    def _svc(self) -> Any:
        return self._service or self._build_service()

    async def verify(self) -> str | None:
        if not self.configured:
            return None

        def _check():
            resp = self._svc().channels().list(part="snippet", mine=True).execute()
            items = resp.get("items", [])
            return items[0]["snippet"]["title"] if items else None

        self.channel_title = await asyncio.to_thread(_check)
        if self.channel_title:
            log_activity("youtube", f"YouTube ulandi: {self.channel_title}")
        return self.channel_title

    async def upload_video(
        self,
        video_path: Path,
        *,
        title: str,
        description: str,
        tags: list[str] | None = None,
        thumbnail_path: Path | None = None,
        privacy: str | None = None,
    ) -> str:
        from googleapiclient.http import MediaFileUpload

        privacy = privacy or env.yt_default_privacy or "private"

        def _upload() -> str:
            svc = self._svc()
            body = {
                "snippet": {
                    "title": title[:100],
                    "description": description[:5000],
                    "tags": (tags or [])[:15],
                    "categoryId": "22",  # People & Blogs
                },
                "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False},
            }
            media = MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True)
            req = svc.videos().insert(part="snippet,status", body=body, media_body=media)
            resp = None
            while resp is None:
                _, resp = req.next_chunk()
            vid_id = resp["id"]
            if thumbnail_path and thumbnail_path.exists():
                try:
                    svc.thumbnails().set(
                        videoId=vid_id, media_body=MediaFileUpload(str(thumbnail_path), mimetype="image/jpeg")
                    ).execute()
                except Exception:
                    pass  # custom thumbnails require phone-verified YouTube channel
            return f"https://youtube.com/watch?v={vid_id}"

        url = await asyncio.to_thread(_upload)
        log_activity("youtube", f"📺 Video yuklandi ({privacy}): {url}")
        return url

    async def update_video_metadata(self, video_id: str, *, title: str, description: str) -> None:
        def _update():
            svc = self._svc()
            cur = svc.videos().list(part="snippet", id=video_id).execute()
            items = cur.get("items", [])
            if not items:
                return
            snippet = items[0]["snippet"]
            snippet["title"] = title[:100]
            snippet["description"] = description[:5000]
            svc.videos().update(part="snippet", body={"id": video_id, "snippet": snippet}).execute()

        await asyncio.to_thread(_update)
        log_activity("youtube", f"✏️ Video metama'lumoti yangilandi: {video_id}")

    async def fetch_recent_comments(self, limit: int = 30) -> list[dict[str, Any]]:
        if not self.configured:
            return []

        def _fetch():
            svc = self._svc()
            ch = svc.channels().list(part="id", mine=True).execute()
            items = ch.get("items", [])
            if not items:
                return []
            channel_id = items[0]["id"]
            resp = svc.commentThreads().list(
                part="snippet", allThreadsRelatedToChannelId=channel_id, maxResults=min(limit, 50), order="time"
            ).execute()
            out = []
            for it in resp.get("items", []):
                top = it["snippet"]["topLevelComment"]
                sn = top["snippet"]
                # Skip our own comments
                if sn.get("authorChannelId", {}).get("value") == channel_id:
                    continue
                if it["snippet"].get("totalReplyCount", 0) > 0:
                    continue
                out.append({
                    "external_id": top["id"],
                    "post_external_id": sn.get("videoId", ""),
                    "author": sn.get("authorDisplayName", "User"),
                    "text": sn.get("textOriginal") or sn.get("textDisplay") or "",
                })
            return out

        return await asyncio.to_thread(_fetch)

    async def reply_comment(self, parent_comment_id: str, text: str) -> str:
        def _reply():
            resp = self._svc().comments().insert(
                part="snippet",
                body={"snippet": {"parentId": parent_comment_id, "textOriginal": text[:2000]}},
            ).execute()
            return resp["id"]

        cid = await asyncio.to_thread(_reply)
        log_activity("youtube", f"💬 YouTube izohiga javob berildi ({parent_comment_id})")
        return cid

    async def moderate_comment(self, comment_id: str, *, reject: bool = True) -> None:
        status = "rejected" if reject else "heldForReview"

        def _mod():
            self._svc().comments().setModerationStatus(id=comment_id, moderationStatus=status).execute()

        await asyncio.to_thread(_mod)
        log_activity("youtube", f"🛡 YouTube izohi moderatsiya qilindi ({status}): {comment_id}")

    async def fetch_channel_stats(self) -> dict[str, Any] | None:
        if not self.configured:
            return None

        def _stats():
            svc = self._svc()
            ch = svc.channels().list(part="snippet,statistics,contentDetails", mine=True).execute()
            items = ch.get("items", [])
            if not items:
                return None
            c = items[0]
            st = c.get("statistics", {})
            uploads_pl = c.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")
            recent_videos = []
            if uploads_pl:
                pl_items = svc.playlistItems().list(part="contentDetails", playlistId=uploads_pl, maxResults=10).execute()
                vids = [x["contentDetails"]["videoId"] for x in pl_items.get("items", [])]
                if vids:
                    vresp = svc.videos().list(part="snippet,statistics", id=",".join(vids)).execute()
                    for v in vresp.get("items", []):
                        vs = v.get("statistics", {})
                        recent_videos.append({
                            "id": v["id"],
                            "title": v["snippet"]["title"],
                            "views": int(vs.get("viewCount", 0)),
                            "likes": int(vs.get("likeCount", 0)),
                            "comments": int(vs.get("commentCount", 0)),
                        })
            return {
                "title": c["snippet"]["title"],
                "followers": int(st.get("subscriberCount", 0)),
                "views": int(st.get("viewCount", 0)),
                "video_count": int(st.get("videoCount", 0)),
                "recent_videos": recent_videos,
            }

        return await asyncio.to_thread(_stats)
