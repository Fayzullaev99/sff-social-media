"""Telegram admin bot: notifications, approvals (inline buttons), escalation answers, KB uploads."""
from __future__ import annotations

import html
import re
from typing import Any

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.approvals import service as approvals
from app.config import env
from app.core import repo, runtime
from app.core.state import is_paused, log_activity, set_paused
from app.db import KnowledgeDoc, session_scope

ESC_TAG = re.compile(r"#E(\d+)")
MAX_PREVIEW = 3000


def h(text: Any) -> str:
    return html.escape(str(text or ""))


class AdminBot:
    def __init__(self):
        self.bot = Bot(env.admin_bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        self.dp = Dispatcher()
        self.router = Router()
        self.dp.include_router(self.router)
        self.connected = False
        # approval_id -> [(chat_id, message_id)] to update messages when decided from the dashboard
        self._approval_msgs: dict[int, list[tuple[int, int]]] = {}
        self._register()
        runtime.subscribe("escalation.created", self.notify_escalation)
        runtime.subscribe("approval.created", self.notify_approval)
        runtime.subscribe("approval.decided", self.on_approval_decided)

    # ------------------------------------------------------------ lifecycle
    async def run(self) -> None:
        me = await self.bot.get_me()
        self.connected = True
        log_activity("admin_bot", f"Admin-bot ishga tushdi: @{me.username}")
        await self.dp.start_polling(self.bot, handle_signals=False)

    async def stop(self) -> None:
        await self.dp.stop_polling()
        await self.bot.session.close()

    async def send_admins(self, text: str, **kw) -> list[tuple[int, int]]:
        sent = []
        for admin_id in env.admin_ids:
            try:
                m = await self.bot.send_message(admin_id, text, **kw)
                sent.append((admin_id, m.message_id))
            except Exception as e:
                log_activity("admin_bot", f"Adminga ({admin_id}) yuborib bo'lmadi: {e}", "warning")
        return sent

    # ------------------------------------------------------------ notifications
    async def notify_escalation(self, esc_id: int) -> None:
        e = repo.get_escalation(esc_id)
        if not e:
            return
        text = (
            f"❓ <b>Javob kerak</b> #E{e['id']}\n"
            f"💬 <b>{h(e['chat_title'])}</b> — {h(e['sender_name'])}\n\n"
            f"<blockquote>{h(e['question'][:MAX_PREVIEW])}</blockquote>\n"
            f"🧠 <i>{h(e['reason'])}</i>\n\n"
            f"↩️ Javob berish uchun <b>shu xabarga reply</b> qiling. Javob foydalanuvchiga yuboriladi va bazaga qo'shiladi."
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🙈 E'tiborsiz qoldirish", callback_data=f"esc:{e['id']}:x"),
        ]])
        await self.send_admins(text, reply_markup=kb)

    def _approval_text(self, a: dict[str, Any]) -> str:
        p = a["payload"] or {}
        lines = [f"<b>{h(a['kind_label'])}</b> · #{a['id']}"]
        if a["requires_money"]:
            amount = f"{a['amount']} {a['currency'] or ''}".strip() if a["amount"] else "—"
            lines.append(f"⚠️ <b>PUL SARFLANADI: {h(amount)}</b>")
        lines.append(h(a["title"]))
        if a["kind"] == "publish_post":
            lines.append(f"\n{h((p.get('preview') or '')[:MAX_PREVIEW])}")
        elif a["kind"] == "publish_video":
            targets = ", ".join(p.get("targets") or []) or "faqat saqlash"
            lines.append(
                f"\n🎬 <b>{h(p.get('title', ''))}</b>\n"
                f"🎨 Uslub: {h(p.get('style', ''))} · ⏱ {h(p.get('duration_sec', 0))}s · 📡 {h(targets)}\n"
                f"<blockquote>{h((p.get('description') or '')[:1200])}</blockquote>"
            )
        elif a["kind"].startswith("ad_"):
            copy = p.get("ad_copy") or {}
            aud = p.get("audience") or {}
            lines.append(
                f"\n🎯 <b>{h(p.get('name', a['title']))}</b>\n"
                + (f"📣 <i>{h(copy.get('headline', ''))}</i>\n{h((copy.get('primary_text') or '')[:900])}\n" if copy else "")
                + (f"👥 Auditoriya: {aud.get('age_min', 18)}–{aud.get('age_max', 45)}, {', '.join(aud.get('locations', [])[:4])}\n" if aud else "")
                + (f"🧠 {h(p.get('rationale', '')[:600])}" if p.get("rationale") else "")
            )
        elif a["kind"] == "send_reply":
            lines.append(f"\n<b>Savol:</b>\n<blockquote>{h(p.get('question', '')[:1000])}</blockquote>")
            lines.append(f"<b>Tayyor javob:</b>\n{h(p.get('text', '')[:MAX_PREVIEW])}")
        elif p:
            lines.append(f"\n<code>{h(str(p)[:1500])}</code>")
        status_map = {
            "pending": "⏳ Kutilmoqda",
            "approved": "✅ Tasdiqlandi",
            "executed": "✅ Bajarildi",
            "rejected": "❌ Rad etildi",
            "failed": "⚠️ Xato",
        }
        lines.append(f"\n<b>Holat:</b> {status_map.get(a['status'], a['status'])}")
        if a.get("result") and a["status"] in ("executed", "failed"):
            lines.append(f"<i>{h(a['result'][:500])}</i>")
        return "\n".join(lines)

    def _approval_kb(self, a: dict[str, Any]) -> InlineKeyboardMarkup | None:
        if a["status"] != "pending":
            return None
        row = [
            InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"ap:{a['id']}:y"),
            InlineKeyboardButton(text="❌ Rad etish", callback_data=f"ap:{a['id']}:n"),
        ]
        rows = [row]
        if a["kind"] == "publish_post":
            rows.append([InlineKeyboardButton(text="🔄 Qayta yozish", callback_data=f"ap:{a['id']}:r")])
        return InlineKeyboardMarkup(inline_keyboard=rows)

    async def notify_approval(self, approval_id: int) -> None:
        a = approvals.get(approval_id)
        if not a:
            return
        sent = await self.send_admins(self._approval_text(a), reply_markup=self._approval_kb(a))
        self._approval_msgs[approval_id] = sent

    async def on_approval_decided(self, a: dict[str, Any]) -> None:
        for chat_id, msg_id in self._approval_msgs.pop(a["id"], []):
            try:
                await self.bot.edit_message_text(self._approval_text(a), chat_id=chat_id, message_id=msg_id)
            except Exception:
                pass

    # ------------------------------------------------------------ handlers
    def _register(self) -> None:
        r = self.router
        admin_filter = F.from_user.id.in_(set(env.admin_ids))

        @r.message(Command("start", "help"), admin_filter)
        async def cmd_help(m: Message):
            await m.answer(
                "🤖 <b>Social Agent — admin panel</b>\n\n"
                "/status — holat va statistika\n"
                "/pause — agentni to'xtatish\n"
                "/resume — agentni yoqish\n"
                "/post [mavzu] — kanal uchun post qoralamasi\n"
                "/video [mavzu] — YouTube/Instagram uchun video yasash\n"
                "/ads [maqsad] — targetolog reklama taklifi (pul tasdiq bilan!)\n"
                "/analytics — reyting, izohlar va sifat tahlili\n"
                "/questions — javobsiz savollar\n"
                "/kb — bilim bazasi hujjatlari\n\n"
                "📎 Fayl (PDF, DOCX, TXT) yuborsangiz — bilim bazasiga qo'shiladi.\n"
                "↩️ ❓ xabariga reply qilsangiz — javob foydalanuvchiga yetkaziladi.\n"
                f"🌐 Dashboard: http://{env.dashboard_host}:{env.dashboard_port}"
            )

        @r.message(Command("status"), admin_filter)
        async def cmd_status(m: Message):
            st = repo.message_stats()
            open_q = len(repo.list_escalations("open"))
            ub = runtime.userbot
            with session_scope() as s:
                docs = s.query(KnowledgeDoc).count()
            allowed = sum(1 for c in repo.list_chats() if c["allowed"])
            await m.answer(
                f"<b>Holat:</b> {'⏸ To‘xtatilgan' if is_paused() else '▶️ Ishlamoqda'}\n"
                f"<b>Telegram:</b> {'🟢 ulangan' if ub and ub.connected else '🔴 ulanmagan'}\n"
                f"<b>Ruxsat berilgan chatlar:</b> {allowed}\n"
                f"<b>Bilim bazasi:</b> {docs} hujjat\n\n"
                f"<b>Oxirgi 24 soat:</b>\n"
                f"📥 Kiruvchi: {st['in']}\n📤 Agent javoblari: {st['out']}\n👤 Siz yozgansiz: {st['owner']}\n"
                f"❓ Javobsiz savollar: {open_q}"
            )

        @r.message(Command("pause"), admin_filter)
        async def cmd_pause(m: Message):
            set_paused(True)
            await m.answer("⏸ Agent to'xtatildi. Yoqish: /resume")

        @r.message(Command("resume"), admin_filter)
        async def cmd_resume(m: Message):
            set_paused(False)
            await m.answer("▶️ Agent ishlamoqda.")

        @r.message(Command("questions"), admin_filter)
        async def cmd_questions(m: Message):
            items = repo.list_escalations("open", limit=10)
            if not items:
                await m.answer("✅ Javobsiz savollar yo'q.")
                return
            for e in items:
                await self.notify_escalation(e["id"])

        @r.message(Command("kb"), admin_filter)
        async def cmd_kb(m: Message):
            with session_scope() as s:
                docs = s.query(KnowledgeDoc).order_by(KnowledgeDoc.id.desc()).limit(30).all()
                lines = [f"#{d.id} · {h(d.title)} ({d.chunk_count})" for d in docs]
            await m.answer("📚 <b>Bilim bazasi</b>\n" + ("\n".join(lines) or "Bo'sh. Fayl yuboring."))

        @r.message(Command("post"), admin_filter)
        async def cmd_post(m: Message, command: CommandObject):
            from app.content import posts

            channels = repo.allowed_channels()
            if not channels:
                await m.answer("Avval dashboard → Chatlar bo'limida kanalga ruxsat bering.")
                return
            from app.core.state import setting

            default_id = setting("content.default_channel_id")
            channel = next((c for c in channels if c["id"] == default_id), channels[0])
            await m.answer(f"✍️ «{h(channel['title'])}» uchun post tayyorlanmoqda...")
            try:
                await posts.create_post(channel["id"], topic=(command.args or None))
            except Exception as e:
                await m.answer(f"⚠️ Xato: {h(e)}")

        @r.message(Command("video"), admin_filter)
        async def cmd_video(m: Message, command: CommandObject):
            from app.content.video import render as video_render

            await m.answer("🎬 Video ssenariy, ovoz va montaj tayyorlanmoqda (15–60 soniya)...")
            try:
                v = await video_render.create_and_render_video(topic=(command.args or None))
                await m.answer(f"✅ Video #{v['id']} tayyor ({v['duration_sec']}s). Tasdiqlash kartasi yuborildi.")
            except Exception as e:
                await m.answer(f"⚠️ Video xatosi: {h(e)}")

        @r.message(Command("ads"), admin_filter)
        async def cmd_ads(m: Message, command: CommandObject):
            from app.ads import strategist

            goal = (command.args or "").strip() or "Obunachilar va buyurtmalarni oshirish"
            await m.answer(f"🎯 Targetolog reklama strategiyasini tayyorlamoqda: «{h(goal)}»...")
            try:
                await strategist.propose_campaign(goal=goal)
            except Exception as e:
                await m.answer(f"⚠️ Targetolog xatosi: {h(e)}")

        @r.message(Command("analytics"), admin_filter)
        async def cmd_analytics(m: Message):
            from app.analytics import monitor

            an = monitor.dashboard_summary()
            sb = an["sentiment_breakdown"]
            guide = an.get("learned_guidance") or "Hozircha yo'q"
            await m.answer(
                f"📊 <b>Analitika va sifat nazorati</b>\n\n"
                f"⭐ Sifat reytingi: <b>{an['quality_rating']}/10</b>\n"
                f"💬 Izohlar: 👍 {sb['positive']} · 😐 {sb['neutral']} · 👎 {sb['negative']} · 🛡 {sb['spam']} spam\n\n"
                f"🧠 <b>O'z-o'zini to'g'irlash ko'rsatmasi:</b>\n<i>{h(guide)}</i>"
            )

        @r.message(F.document, admin_filter)
        async def on_document(m: Message):
            from app.knowledge import store

            doc = m.document
            if doc.file_size and doc.file_size > 20 * 1024 * 1024:
                await m.answer("Fayl juda katta (20 MB gacha).")
                return
            await m.answer("📥 Bazaga qo'shilmoqda...")
            try:
                f = await self.bot.download(doc)
                kd = await store.add_file(doc.file_name or "file.txt", f.read())
                await m.answer(f"✅ «{h(kd.title)}» qo'shildi ({kd.chunk_count} bo'lak).")
            except Exception as e:
                await m.answer(f"⚠️ Xato: {h(e)}")

        @r.message(F.reply_to_message, F.text, admin_filter)
        async def on_reply(m: Message):
            src = m.reply_to_message.text or m.reply_to_message.caption or ""
            match = ESC_TAG.search(src)
            if not match:
                return
            esc_id = int(match.group(1))
            try:
                e = await repo.answer_escalation(esc_id, m.text, by=f"tg:{m.from_user.id}")
                await m.answer(f"✅ Javob yuborildi va bazaga qo'shildi (#E{e['id']}).")
            except Exception as ex:
                await m.answer(f"⚠️ Xato: {h(ex)}")

        @r.callback_query(F.data.startswith("ap:"), admin_filter)
        async def on_approval_cb(c: CallbackQuery):
            _, sid, action = c.data.split(":")
            approval_id = int(sid)
            if action == "r":
                from app.content import posts

                a = approvals.get(approval_id)
                await c.answer("🔄 Qayta yozilmoqda...")
                try:
                    await posts.regenerate_post(int(a["payload"]["post_id"]))
                    a = approvals.get(approval_id)
                    await c.message.edit_text(self._approval_text(a), reply_markup=self._approval_kb(a))
                except Exception as e:
                    await c.message.answer(f"⚠️ Xato: {h(e)}")
                return
            await c.answer("⏳")
            # Remove this message from the map so on_approval_decided doesn't double-edit it
            msgs = self._approval_msgs.get(approval_id, [])
            self._approval_msgs[approval_id] = [x for x in msgs if x != (c.message.chat.id, c.message.message_id)]
            try:
                a = await approvals.decide(approval_id, action == "y", decided_by=f"tg:{c.from_user.id}")
                await c.message.edit_text(self._approval_text(a))
            except Exception as e:
                await c.message.answer(f"⚠️ Xato: {h(e)}")

        @r.callback_query(F.data.startswith("esc:"), admin_filter)
        async def on_esc_cb(c: CallbackQuery):
            _, sid, _action = c.data.split(":")
            repo.dismiss_escalation(int(sid))
            await c.answer("Yopildi")
            await c.message.edit_reply_markup(reply_markup=None)

        @r.message()
        async def fallback(m: Message):
            if m.from_user and m.from_user.id not in env.admin_ids:
                await m.answer("⛔ Bu bot faqat admin uchun.")
