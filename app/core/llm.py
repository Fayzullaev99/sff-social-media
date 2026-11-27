"""Thin async wrapper around the Gemini API (google-genai SDK)."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Type, TypeVar

import numpy as np
from google import genai
from google.genai import types
from pydantic import BaseModel

log = logging.getLogger("agent.llm")

T = TypeVar("T", bound=BaseModel)

EMBED_DIM = 768
_EMBED_BATCH = 50


class LLM:
    def __init__(self, api_key: str, model: str, embed_model: str):
        if not api_key:
            raise ValueError("GEMINI_API_KEY bo'sh")
        self.client = genai.Client(api_key=api_key)
        self.model = model
        self.embed_model = embed_model

    async def _retry(self, fn, *, attempts: int = 4):
        delay = 2.0
        for i in range(attempts):
            try:
                return await fn()
            except Exception as e:  # network / quota / 5xx
                if i == attempts - 1:
                    raise
                log.warning("Gemini xatosi (%s), %.0fs dan keyin qayta urinish", e, delay)
                await asyncio.sleep(delay)
                delay *= 2

    async def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.7,
    ) -> str:
        config = types.GenerateContentConfig(system_instruction=system, temperature=temperature)

        async def call():
            resp = await self.client.aio.models.generate_content(
                model=self.model, contents=prompt, config=config
            )
            return (resp.text or "").strip()

        return await self._retry(call)

    async def generate_json(
        self,
        prompt: str,
        schema: Type[T],
        *,
        system: str | None = None,
        temperature: float = 0.6,
    ) -> T:
        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=temperature,
            response_mime_type="application/json",
            response_schema=schema,
        )

        async def call():
            resp = await self.client.aio.models.generate_content(
                model=self.model, contents=prompt, config=config
            )
            parsed = getattr(resp, "parsed", None)
            if isinstance(parsed, schema):
                return parsed
            return schema.model_validate(json.loads(resp.text or "{}"))

        return await self._retry(call)

    async def embed(self, texts: list[str], *, query: bool = False) -> np.ndarray:
        """Return L2-normalised float32 matrix (len(texts), EMBED_DIM)."""
        if not texts:
            return np.zeros((0, EMBED_DIM), dtype=np.float32)
        vectors: list[list[float]] = []
        task = "RETRIEVAL_QUERY" if query else "RETRIEVAL_DOCUMENT"
        for start in range(0, len(texts), _EMBED_BATCH):
            batch = texts[start : start + _EMBED_BATCH]

            async def call(batch=batch):
                return await self.client.aio.models.embed_content(
                    model=self.embed_model,
                    contents=batch,
                    config=types.EmbedContentConfig(task_type=task, output_dimensionality=EMBED_DIM),
                )

            resp = await self._retry(call)
            vectors.extend(e.values for e in resp.embeddings)
        arr = np.asarray(vectors, dtype=np.float32)
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return arr / norms


def dump(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)
