"""Telegram personal account automation (Telethon userbot).

- Replies automatically ONLY in whitelisted chats (dashboard -> Chatlar).
- Collects several quick messages into one reply (debounce), shows "typing…", respects rate limits.
- If you write in a chat yourself, the agent stays silent there for a while (human takeover).
- Replies to comments in the discussion groups of allowed channels.
"""
from __future__ import annotations

import asyncio
import random
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from telethon import TelegramClient, events, utils
from telethon.tl import types as tl

from app.approvals import service as approvals
from app.config import env
from app.core import brain, repo
from app.core.brain import HistoryItem
from app.core.policy import rate_limiter, within_working_hours
from app.core.state import get_settings, is_paused, log_activity

TG_LIMIT = 4000


@dataclass
class Pending:
    task: asyncio.Task | None = None
    cancellable: bool = True
    triggers: list[HistoryItem] = field(default_factory=list)
    trigger_db_ids: set[int] = field(default_factory=set)
    reply_to: int | None = None
    sender_name: str = ""
    extra_context: str = ""


def split_text(text: str, limit: int = TG_LIMIT) -> list[str]:
    parts: list[str] = []
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = text.rfind(" ", 0, limit)
        if cut <= 0:
            cut = limit
        parts.append(text[:cut].strip())
        text = text[cut:].strip()
    if text:
        parts.append(text)
    return parts


class UserBot:
    def __init__(self):
        self.client = TelegramClient(
            env.session_path,
            env.tg_api_id,
            env.tg_api_hash,
            device_model="Social Agent",
            system_version="Windows",
            app_version="1.0",
        )
        self.me: Any = None
        self.connected = False
        self._pending: dict[int, Pending] = {}
        self._locks: dict[int, asyncio.Lock] = {}
        self._sent_ids: deque[tuple[int, int]] = deque(maxlen=2000)
        self._sending_text: dict[int, str] = {}
        self._owner_activity: dict[int, float] = {}

    # ------------------------------------------------------------ lifecycle
    async def start(self) -> None:
        await self.client.connect()
        if not await self.client.is_user_authorized():
            raise RuntimeError("Telegram akkauntga kirilmagan. Avval bir marta: .venv\\Scripts\\python login.py")
        self.me = await self.client.get_me()
        await self.client.get_dialogs(limit=300)  # warm entity cache
        self.client.add_event_handler(self._on_incoming, events.NewMessage(incoming=True))
        self.client.add_event_handler(self._on_outgoing, events.NewMessage(outgoing=True))
        self.connected = True
        log_activity("telegram", f"Userbot ulandi: {utils.get_display_name(self.me)} (@{self.me.username or '-'})")

    async def run(self) -> None:
        await self.client.run_until_disconnected()
        self.connected = False

    async def stop(self) -> None:
        await self.client.disconnect()
        self.connected = False

    # ------------------------------------------------------------ helpers
    def _lock(self, chat_id: int) -> asyncio.Lock:
        return self._locks.setdefault(chat_id, asyncio.Lock())

    @staticmethod
    def _behavior() -> dict[str, Any]:
        return get_settings().get("behavior", {})

    def _taken_over(self, chat_id: int) -> bool:
        minutes = float(self._behavior().get("human_takeover_minutes", 10))
        last = self._owner_activity.get(chat_id)
        return last is not None and (time.monotonic() - last) < minutes * 60

    # ------------------------------------------------------------ events
    async def _on_outgoing(self, event: events.NewMessage.Event) -> None:
        chat_id = event.chat_id
        key = (chat_id, event.message.id)
        if key in self._sent_ids or self._sending_text.get(chat_id) == (event.raw_text or ""):
            return  # sent by the agent itself
        chat = repo.get_allowed_chat(chat_id)
        if not chat or chat["kind"] == "channel":
            return
        # The owner wrote manually -> pause the agent in this chat for a while
        self._owner_activity[chat_id] = time.monotonic()
        p = self._pending.get(chat_id)
        if p and p.task and p.cancellable:
            p.task.cancel()
            self._pending.pop(chat_id, None)
        repo.log_message(chat_id, "owner", event.raw_text or "", tg_message_id=event.message.id,
                         sender_name="Siz")

    async def _on_incoming(self, event: events.NewMessage.Event) -> None:
        try:
            await self._handle_incoming(event)
        except Exception as e:
            log_activity("telegram", f"Xabarni qayta ishlashda xato: {e}", "error")

    async def _handle_incoming(self, event: events.NewMessage.Event) -> None:
        chat_id = event.chat_id
        chat = repo.get_allowed_chat(chat_id)
        if not chat:
            return
        msg = event.message
        sender = await event.get_sender()
        if isinstance(sender, tl.User) and sender.bot:
            return
        if isinstance(sender, tl.Channel):
            return  # auto-forwarded channel post (discussion group) or "send as channel"
        text = (event.raw_text or "").strip()
        if not text:
            if msg.media and event.is_private:
                text = "[foydalanuvchi matnsiz media yubordi: rasm/ovoz/fayl]"
            else:
                return
        sender_name = utils.get_display_name(sender) if sender else "Foydalanuvchi"

        if event.is_private:
            context = "private"
        elif chat["kind"] == "discussion":
            context = "comment"
        else:
            context = "group"

        db_id = repo.log_message(chat_id, "in", text, tg_message_id=msg.id,
                                 sender_id=getattr(sender, "id", None), sender_name=sender_name)

        if context == "group":
            b = self._behavior()
            keywords = [k.lower() for k in b.get("group_trigger_keywords", []) or []]
            addressed = bool(msg.mentioned) or any(k in text.lower() for k in keywords)
            if b.get("reply_in_groups_only_when_mentioned", True) and not addressed:
                return

        extra = ""
        if context == "comment" and msg.reply_to:
            try:
                parent = await msg.get_reply_message()
                if parent and parent.raw_text:
                    extra = f"CHANNEL POST BEING COMMENTED ON:\n{parent.raw_text[:1500]}"
            except Exception:
                pass

        p = self._pending.get(chat_id)
        if p and p.cancellable and p.task and not p.task.done():
            p.task.cancel()
        else:
            p = Pending()
            self._pending[chat_id] = p
        p.triggers.append(HistoryItem(author=sender_name, text=text))
        p.trigger_db_ids.add(db_id)
        p.reply_to = msg.id
        p.sender_name = sender_name
        p.extra_context = extra or p.extra_context
        p.cancellable = True
        p.task = asyncio.create_task(self._process(chat_id, chat, context, p))

    # ------------------------------------------------------------ reply pipeline
    async def _process(self, chat_id: int, chat: dict[str, Any], context: str, p: Pending) -> None:
        b = self._behavior()
        try:
            await asyncio.sleep(float(b.get("debounce_sec", 4)))
            async with self._lock(chat_id):
                if is_paused() or not b.get("auto_reply_enabled", True):
                    return
                if not within_working_hours():
                    return
                if self._taken_over(chat_id):
                    return
                history_rows = repo.recent_messages(chat_id, int(b.get("history_messages", 20)),
                                                    exclude_ids=p.trigger_db_ids)
                history = [
                    HistoryItem(author=r["sender_name"] or "User", text=r["text"],
                                is_self=r["direction"] in ("out", "owner"))
                    for r in history_rows
                ]
                result = await brain.decide_reply(
                    chat_title=chat["title"], context=context,  # type: ignore[arg-type]
                    history=history, new_messages=list(p.triggers), extra_context=p.extra_context,
                )
                p.cancellable = False  # from here on we commit to the reply
                d = result.decision
                question = "\n".join(t.text for t in p.triggers)

                if result.escalate:
                    await repo.create_escalation(
                        chat_id=chat_id, chat_title=chat["title"], tg_message_id=p.reply_to,
                        sender_name=p.sender_name, question=question, language=d.language,
                        reason=d.reason or f"Ishonch past ({d.confidence:.2f})",
                    )
                if not d.should_reply or not d.reply.strip():
                    return

                reply_to = None if context == "private" else p.reply_to
                if chat["mode"] == "approve":
                    await approvals.request(
                        "send_reply",
                        f"{chat['title']}: {question[:80]}",
                        {"chat_id": chat_id, "reply_to": reply_to, "text": d.reply,
                         "question": question, "chat_title": chat["title"]},
                    )
                    return

                for _ in range(12):  # wait up to ~60s for the rate limiter
                    if rate_limiter.allow(chat_id):
                        break
                    await asyncio.sleep(5)
                else:
                    log_activity("telegram", f"Rate limit: {chat['title']} ga javob o'tkazib yuborildi", "warning")
                    return
                await self.send_humanlike(chat_id, d.reply, reply_to=reply_to, language=d.language)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log_activity("telegram", f"{chat['title']}: javob tayyorlashda xato: {e}", "error")
        finally:
            if self._pending.get(chat_id) is p and (p.task is None or p.task.done() or not p.cancellable):
                self._pending.pop(chat_id, None)

    async def send_humanlike(
        self,
        chat_id: int,
        text: str,
        *,
        reply_to: int | None = None,
        language: str | None = None,
        quick: bool = False,
    ) -> list[int]:
        b = self._behavior()
        try:
            await self.client.send_read_acknowledge(chat_id)
        except Exception:
            pass
        if not quick:
            await asyncio.sleep(random.uniform(float(b.get("reply_delay_min_sec", 2)),
                                               float(b.get("reply_delay_max_sec", 8))))
        ids: list[int] = []
        for i, part in enumerate(split_text(text)):
            typing = min(len(part) / max(float(b.get("typing_chars_per_sec", 14)), 1.0),
                         float(b.get("max_typing_sec", 15)))
            if quick:
                typing = min(typing, 3)
            try:
                async with self.client.action(chat_id, "typing"):
                    await asyncio.sleep(typing)
            except Exception:
                await asyncio.sleep(typing)
            self._sending_text[chat_id] = part
            try:
                m = await self.client.send_message(chat_id, part, reply_to=reply_to if i == 0 else None)
            finally:
                self._sending_text.pop(chat_id, None)
            self._sent_ids.append((chat_id, m.id))
            ids.append(m.id)
            rate_limiter.record(chat_id)
            repo.log_message(chat_id, "out", part, tg_message_id=m.id, sender_name="Agent", language=language)
        return ids

    # ------------------------------------------------------------ channels & dialogs
    async def publish(self, channel_id: int, text: str, media_path: str | None = None) -> int:
        self._sending_text[channel_id] = text
        try:
            if media_path:
                m = await self.client.send_file(channel_id, media_path, caption=text[:1024], parse_mode="md")
            else:
                m = await self.client.send_message(channel_id, text, parse_mode="md", link_preview=False)
        finally:
            self._sending_text.pop(channel_id, None)
        self._sent_ids.append((channel_id, m.id))
        return m.id

    async def list_dialogs(self, limit: int = 300) -> list[dict[str, Any]]:
        out = []
        async for d in self.client.iter_dialogs(limit=limit):
            e = d.entity
            if d.is_user:
                if getattr(e, "is_self", False):
                    continue
                kind = "bot" if getattr(e, "bot", False) else "user"
            elif d.is_channel and getattr(e, "broadcast", False):
                kind = "channel"
            else:
                kind = "group"
            out.append({
                "id": d.id,
                "title": d.name or "",
                "username": getattr(e, "username", None),
                "kind": kind,
                "unread": d.unread_count,
                "can_post": kind != "channel" or bool(getattr(e, "creator", False) or getattr(e, "admin_rights", None)),
            })
        return out

    async def linked_discussion_id(self, channel_id: int) -> int | None:
        from telethon.tl.functions.channels import GetFullChannelRequest

        full = await self.client(GetFullChannelRequest(await self.client.get_input_entity(channel_id)))
        linked = getattr(full.full_chat, "linked_chat_id", None)
        return utils.get_peer_id(tl.PeerChannel(linked)) if linked else None


# ---------------------------------------------------------------- approval handlers
@approvals.on_approve("send_reply")
async def _approved_reply(payload: dict[str, Any], approval_id: int) -> str:
    from app.core import runtime

    if not runtime.userbot or not runtime.userbot.connected:
        raise RuntimeError("Userbot ulanmagan")
    ids = await runtime.userbot.send_humanlike(payload["chat_id"], payload["text"],
                                               reply_to=payload.get("reply_to"), quick=True)
    return f"Yuborildi (msg {ids})"
