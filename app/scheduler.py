"""Lightweight background scheduler: scheduled posts, social comments, analytics, ads & daily reports."""
from __future__ import annotations

import asyncio
import time
from datetime import date, datetime

from app.core import repo, runtime
from app.core.state import get_settings, is_paused, log_activity


class Scheduler:
    def __init__(self, tick_sec: int = 30):
        self.tick_sec = tick_sec
        self._done_today: dict[str, date] = {}
        self._last_run: dict[str, float] = {}

    def _due_daily(self, key: str, hhmm: str | None, now: datetime) -> bool:
        if not hhmm:
            return False
        try:
            hh, mm = map(int, str(hhmm).split(":"))
        except ValueError:
            return False
        if (now.hour, now.minute) < (hh, mm):
            return False
        if self._done_today.get(key) == now.date():
            return False
        self._done_today[key] = now.date()
        return True

    def _due_every(self, key: str, minutes: float) -> bool:
        if minutes <= 0:
            return False
        now = time.monotonic()
        last = self._last_run.get(key, 0.0)
        if now - last < minutes * 60:
            return False
        self._last_run[key] = now
        return True

    async def run(self) -> None:
        now = datetime.now()
        cfg = get_settings()
        for key, hhmm in (
            ("report", cfg.get("reports", {}).get("daily_report_time")),
            ("drafts", cfg.get("content", {}).get("draft_time")),
        ):
            try:
                hh, mm = map(int, str(hhmm).split(":"))
                if (now.hour, now.minute) >= (hh, mm):
                    self._done_today[key] = now.date()
            except (ValueError, TypeError):
                pass
        while True:
            try:
                await self.tick()
            except Exception as e:
                log_activity("scheduler", f"Xato: {e}", "error")
            await asyncio.sleep(self.tick_sec)

    async def tick(self) -> None:
        from app.ads import strategist
        from app.analytics import monitor, sentiment
        from app.content import posts

        await posts.publish_due_posts()
        now = datetime.now()
        cfg = get_settings()

        if self._due_daily("report", cfg.get("reports", {}).get("daily_report_time"), now):
            await self.daily_report()

        if is_paused():
            return

        # 1. Poll YouTube & Instagram comments (auto-reply + sentiment + spam moderation)
        scfg = cfg.get("social", {})
        if self._due_every("comments", float(scfg.get("poll_comments_minutes", 10))):
            try:
                await sentiment.poll_all_comments()
            except Exception as e:
                log_activity("scheduler", f"Izohlarni tekshirishda xato: {e}", "warning")

        # 2. Periodic analytics, quality audit & self-correction + active ad guard
        if self._due_every("analytics", float(scfg.get("analytics_interval_minutes", 60))):
            try:
                await monitor.collect_metrics()
                if runtime.llm:
                    await monitor.run_quality_audit()
                await strategist.optimize_active_campaigns()
            except Exception as e:
                log_activity("scheduler", f"Analitika siklida xato: {e}", "warning")

        # 3. Daily content drafts (still require admin approval!)
        content = cfg.get("content", {})
        n = int(content.get("daily_drafts", 0) or 0)
        if n > 0 and runtime.llm and self._due_daily("drafts", content.get("draft_time"), now):
            channels = repo.allowed_channels()
            default_id = content.get("default_channel_id")
            channel = next((c for c in channels if c["id"] == default_id), channels[0] if channels else None)
            if channel:
                for _ in range(n):
                    try:
                        await posts.create_post(channel["id"])
                    except Exception as e:
                        log_activity("content", f"Avto-qoralama xatosi: {e}", "error")

    async def daily_report(self) -> None:
        if not runtime.admin_bot:
            return
        from app.analytics import monitor

        st = repo.message_stats()
        open_q = repo.list_escalations("open")
        an = monitor.dashboard_summary()
        sb = an["sentiment_breakdown"]
        text = (
            "📊 <b>Kunlik hisobot</b>\n\n"
            f"📥 Kiruvchi xabarlar: {st['in']}\n"
            f"📤 Agent javoblari: {st['out']}\n"
            f"👤 Siz yozgansiz: {st['owner']}\n"
            f"❓ Javobsiz savollar: {len(open_q)}\n\n"
            f"⭐ Sifat reytingi: <b>{an['quality_rating']}/10</b>\n"
            f"💬 Izohlar: 👍 {sb['positive']} · 😐 {sb['neutral']} · 👎 {sb['negative']} · 🛡 {sb['spam']} spam"
        )
        await runtime.admin_bot.send_admins(text)
