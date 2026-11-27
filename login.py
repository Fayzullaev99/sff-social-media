"""One-time interactive Telegram login for the userbot session.

    .venv\\Scripts\\python login.py

Telegram sends a code to your app; enter it here (and your 2FA password if enabled).
The session is saved to data/ and reused by run.py. Never share the session file!
"""
import asyncio

from telethon import TelegramClient

from app.config import env


async def main() -> None:
    if not env.telegram_configured:
        print("❌ .env faylida TG_API_ID va TG_API_HASH ni kiriting (https://my.telegram.org)")
        return
    client = TelegramClient(env.session_path, env.tg_api_id, env.tg_api_hash,
                            device_model="Social Agent", system_version="Windows", app_version="1.0")
    await client.start()  # prompts for phone, code and 2FA password
    me = await client.get_me()
    print(f"✅ Kirildi: {me.first_name} (@{me.username}) — id: {me.id}")
    print("Endi agentni ishga tushiring:  .venv\\Scripts\\python run.py")
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
