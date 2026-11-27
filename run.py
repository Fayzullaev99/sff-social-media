"""Social Agent — entry point.

    .venv\\Scripts\\python run.py

Starts (whatever is configured in .env): Telegram userbot, admin bot, scheduler and the web dashboard.
"""
from __future__ import annotations

import asyncio
import logging
import sys

import uvicorn

from app.config import env
from app.core import runtime
from app.core.state import log_activity
from app.db import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logging.getLogger("telethon").setLevel(logging.WARNING)
logging.getLogger("aiogram").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("agent")


async def main() -> None:
    init_db()

    # Register approval handlers
    import app.ads.strategist  # noqa: F401
    import app.channels.telegram_userbot  # noqa: F401
    import app.content.posts  # noqa: F401
    import app.content.video.render  # noqa: F401

    tasks: list[asyncio.Task] = []

    if env.gemini_api_key:
        from app.core.llm import LLM

        runtime.llm = LLM(env.gemini_api_key, env.gemini_model, env.gemini_embed_model)
    else:
        log.warning("GEMINI_API_KEY yo'q — AI funksiyalari o'chiq")

    # YouTube & Instagram channels (official APIs)
    from app.channels.instagram import InstagramChannel
    from app.channels.youtube import YouTubeChannel

    runtime.youtube = YouTubeChannel()
    if runtime.youtube.configured:
        try:
            await runtime.youtube.verify()
        except Exception as e:
            log_activity("youtube", f"YouTube tekshiruvda xato: {e}", "warning")

    runtime.instagram = InstagramChannel()
    if runtime.instagram.configured:
        try:
            await runtime.instagram.verify()
        except Exception as e:
            log_activity("instagram", f"Instagram tekshiruvda xato: {e}", "warning")

    if env.admin_bot_configured:
        from app.admin.bot import AdminBot

        runtime.admin_bot = AdminBot()
        tasks.append(asyncio.create_task(runtime.admin_bot.run(), name="admin_bot"))
    else:
        log.warning("ADMIN_BOT_TOKEN yoki ADMIN_IDS yo'q — admin-bot o'chiq")

    if env.telegram_configured:
        from app.channels.telegram_userbot import UserBot

        ub = UserBot()
        try:
            await ub.start()
            runtime.userbot = ub
            tasks.append(asyncio.create_task(ub.run(), name="userbot"))
        except Exception as e:
            log_activity("telegram", f"Userbot ishga tushmadi: {e}", "error")
    else:
        log.warning("TG_API_ID/TG_API_HASH yo'q — Telegram userbot o'chiq")

    from app.scheduler import Scheduler

    tasks.append(asyncio.create_task(Scheduler().run(), name="scheduler"))

    from app.web.server import app as web_app

    server = uvicorn.Server(uvicorn.Config(web_app, host=env.dashboard_host, port=env.dashboard_port,
                                           log_level="warning"))
    tasks.append(asyncio.create_task(server.serve(), name="web"))
    log_activity("agent", f"Social Agent ishga tushdi · Dashboard: http://{env.dashboard_host}:{env.dashboard_port}")

    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
        for t in done:
            if t.exception():
                log.error("%s to'xtadi: %s", t.get_name(), t.exception())
    finally:
        for t in tasks:
            t.cancel()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
