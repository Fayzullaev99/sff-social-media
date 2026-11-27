"""Gemini-powered video script generator grounded in the knowledge base."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.content.posts import _random_knowledge
from app.core import runtime
from app.core.state import get_settings
from app.knowledge import store


class SceneSpec(BaseModel):
    narration: str = Field(description="Spoken voiceover line for this scene (natural, conversational)")
    on_screen_text: str = Field(description="Short punchy caption shown on screen (3-8 words)")
    visual_query: str = Field(description="English stock footage / visual search query (2-5 words)")
    visual_prompt: str = Field(description="Detailed visual prompt in English for AI video generation if used")


class VideoScript(BaseModel):
    title: str = Field(description="Catchy SEO title (max 90 chars)")
    description: str = Field(description="Platform description with hashtags and CTA")
    tags: list[str] = Field(description="5-12 SEO tags without #")
    recommended_style: Literal["stock", "kinetic", "ai_veo", "avatar"] = Field(
        description="Best visual style for this topic: stock (real-life footage), kinetic (facts/tips/quotes), ai_veo (cinematic/conceptual), avatar (talking spokesperson)"
    )
    scenes: list[SceneSpec] = Field(description="4 to 6 short scenes totaling 25-55 seconds")


async def generate_video_script(
    topic: str | None,
    *,
    language: str = "uz",
    aspect_ratio: str = "9:16",
    instructions: str = "",
) -> VideoScript:
    llm = runtime.require_llm()
    p = get_settings().get("persona", {})
    if topic:
        hits = await store.search(topic, k=5)
        knowledge = [f"(source: {h.doc_title})\n{h.text}" for h in hits]
    else:
        knowledge = _random_knowledge(5)

    fmt = "vertical Short / Reel (9:16, 30-50 seconds, fast hook in first 2 seconds)" if aspect_ratio == "9:16" else "horizontal YouTube video (16:9, 45-90 seconds)"
    learned = get_settings().get("content", {}).get("learned_guidance", "")
    prompt = f"""Create a complete video script for a {fmt}.
Author: {p.get('owner_name', 'Admin')} — {p.get('role', '')}
Style: {p.get('style', '')}
Language for narration, on_screen_text, title, description: {language} (Uzbek in Latin script unless specified).
Topic: {topic or 'Choose the highest-value engaging topic from KNOWLEDGE'}
{('Extra instructions: ' + instructions) if instructions else ''}
{('Audience feedback self-correction guidance: ' + learned) if learned else ''}

Rules:
- Specific facts (prices, services, dates, contacts) MUST come strictly from KNOWLEDGE. Never invent facts.
- Scene 1 MUST be a strong scroll-stopping hook.
- Final scene MUST include a natural call-to-action (subscribe, comment, DM).
- Keep each scene narration to 1-2 short natural sentences (12-22 words) so voiceover pacing feels crisp and human.
- visual_query and visual_prompt MUST be in English.

KNOWLEDGE:
{chr(10).join(knowledge) or '(empty — write an engaging general educational/tips video without inventing company facts)'}"""
    return await llm.generate_json(prompt, VideoScript, temperature=0.85)
