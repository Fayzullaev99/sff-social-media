"""The agent's "brain": builds prompts from persona + knowledge + history and decides how to reply."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

from app.core import runtime
from app.core.state import get_settings
from app.knowledge import store

ChatContext = Literal["private", "group", "comment"]


class AgentDecision(BaseModel):
    should_reply: bool = Field(description="false if no reply is needed (spam, not addressed, conversation naturally ended)")
    reply: str = Field(description="The message text to send (empty if should_reply is false)")
    language: str = Field(description="ISO code of the user's language, e.g. uz, ru, en, tr")
    confidence: float = Field(description="0..1 — how sure you are the reply is correct and grounded")
    needs_admin: bool = Field(description="true if the owner must answer or decide personally")
    reason: str = Field(description="Short internal note (in Uzbek) why admin is needed or what you did")


@dataclass
class HistoryItem:
    author: str  # display name, or "SEN" for the agent/owner
    text: str
    is_self: bool = False


@dataclass
class BrainResult:
    decision: AgentDecision
    hits: list[store.SearchHit] = field(default_factory=list)
    escalate: bool = False


def _system_prompt(context: ChatContext) -> str:
    cfg = get_settings()
    p = cfg.get("persona", {})
    owner = p.get("owner_name", "Admin")
    honesty = (
        f"- If someone SINCERELY asks whether they are talking to a bot/AI, do not deny it: say you are "
        f"{owner}'s AI assistant and that {owner} can also answer personally.\n"
        if p.get("disclose_ai_if_asked", True)
        else ""
    )
    context_rules = {
        "private": "This is a private chat. Be warm and personal, like a real human conversation.",
        "group": "This is a group chat. Reply only if the message is addressed to you or is clearly a question you should answer. Keep it short.",
        "comment": "This is a PUBLIC comment under a channel post. Be polite, concise (1-3 sentences) and never reveal private information. Thank people for positive feedback; for complaints apologise, address the issue factually and invite them to a private message if needed. Ignore spam (should_reply=false).",
    }[context]
    return f"""You are writing on Telegram on behalf of {owner} — {p.get('role', '')}.
Write as a natural human would: no robotic phrases, no "As an AI…", no long lists unless asked.

STYLE: {p.get('style', '')}

LANGUAGE:
- Detect the language of the newest user message(s) and reply in EXACTLY that language.
- For Uzbek, match the script the user used (Latin or Cyrillic).
- If the language is unclear, use "{p.get('default_language', 'uz')}".

FACTS AND KNOWLEDGE:
- Specific facts (prices, products, services, addresses, schedules, policies, promises, contacts) must come ONLY from the KNOWLEDGE section. Never invent or guess them.
- Greetings, small talk, and widely known general knowledge are fine without KNOWLEDGE.
- If answering requires facts that are NOT in KNOWLEDGE, or a personal decision/commitment from {owner} (meetings, discounts, payments, refunds, partnerships, personal matters), set needs_admin=true and make `reply` a short natural message in the user's language saying you will check and get back to them shortly. Do NOT mention "admin", "database" or "knowledge base".
- NEVER agree to any payment, money transfer, discount, refund or financial commitment yourself — always needs_admin=true.
{honesty}
CONTEXT: {context_rules}

FORMAT: plain Telegram text. No markdown headings. Keep replies reasonably short.
confidence: 1.0 = fully grounded/obvious, below 0.6 = unsure.
{p.get('extra_instructions', '')}""".strip()


def _format_history(history: list[HistoryItem]) -> str:
    if not history:
        return "(no previous messages)"
    lines = []
    for h in history:
        who = "SEN (you)" if h.is_self else h.author
        lines.append(f"[{who}]: {h.text}")
    return "\n".join(lines)


def _format_hits(hits: list[store.SearchHit]) -> str:
    if not hits:
        return "(nothing relevant found)"
    return "\n\n".join(
        f"[{i}] (source: {h.doc_title}; relevance {h.score:.2f})\n{h.text}" for i, h in enumerate(hits, 1)
    )


async def decide_reply(
    *,
    chat_title: str,
    context: ChatContext,
    history: list[HistoryItem],
    new_messages: list[HistoryItem],
    extra_context: str = "",
) -> BrainResult:
    llm = runtime.require_llm()
    query = "\n".join(m.text for m in new_messages)[-2000:]
    hits = await store.search(query, k=6)
    prompt = f"""CHAT: {chat_title} ({context})
{extra_context}

KNOWLEDGE:
{_format_hits(hits)}

CONVERSATION HISTORY (oldest → newest):
{_format_history(history)}

NEW MESSAGE(S) TO RESPOND TO:
{_format_history(new_messages)}"""
    decision = await llm.generate_json(prompt, AgentDecision, system=_system_prompt(context))
    min_conf = float(get_settings().get("behavior", {}).get("min_confidence", 0.6))
    escalate = decision.needs_admin or (decision.should_reply and decision.confidence < min_conf)
    return BrainResult(decision=decision, hits=hits, escalate=escalate)


async def polish_admin_answer(question: str, answer: str, language: str) -> str:
    """Turn the owner's quick answer into a natural reply in the user's language."""
    llm = runtime.require_llm()
    p = get_settings().get("persona", {})
    prompt = f"""A customer asked: «{question}»
The owner ({p.get('owner_name', 'Admin')}) answered briefly: «{answer}»

Rewrite the owner's answer as a natural, friendly reply to the customer in language "{language}"
(style: {p.get('style', '')}). Keep ALL facts exactly as given, do not add new facts.
Return only the reply text."""
    return await llm.generate(prompt, temperature=0.4)
