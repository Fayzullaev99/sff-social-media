"""Knowledge base: text extraction, chunking, embedding storage and semantic search."""
from __future__ import annotations

import asyncio
import io
import re
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.core import runtime
from app.core.llm import EMBED_DIM
from app.core.state import log_activity
from app.db import KnowledgeChunk, KnowledgeDoc, session_scope

SUPPORTED_EXT = {".pdf", ".docx", ".txt", ".md", ".csv", ".json", ".html", ".htm"}


# ---------------------------------------------------------------- extraction
def extract_text(filename: str, data: bytes) -> str:
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        return "\n\n".join((p.extract_text() or "") for p in reader.pages)
    if ext == ".docx":
        import docx

        d = docx.Document(io.BytesIO(data))
        parts = [p.text for p in d.paragraphs]
        for table in d.tables:
            for row in table.rows:
                parts.append(" | ".join(c.text.strip() for c in row.cells))
        return "\n".join(parts)
    if ext in (".html", ".htm"):
        return html_to_text(data.decode("utf-8", errors="ignore"))
    if ext in SUPPORTED_EXT:
        return data.decode("utf-8", errors="ignore")
    raise ValueError(f"Qo'llab-quvvatlanmaydigan fayl turi: {ext}")


def html_to_text(html: str) -> str:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()
    return soup.get_text("\n")


async def fetch_url_text(url: str) -> tuple[str, str]:
    import httpx

    async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
        r = await client.get(url, headers={"User-Agent": "Mozilla/5.0 SocialAgent"})
        r.raise_for_status()
    from bs4 import BeautifulSoup

    title = (BeautifulSoup(r.text, "html.parser").title or None)
    return (title.get_text().strip() if title else url), html_to_text(r.text)


# ---------------------------------------------------------------- chunking
def normalize(text: str) -> str:
    text = text.replace("\r", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_text(text: str, size: int = 1000, overlap: int = 150) -> list[str]:
    """Paragraph-aware chunking with character overlap."""
    text = normalize(text)
    if not text:
        return []
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    buf = ""
    for para in paragraphs:
        while len(para) > size:  # very long paragraph -> hard split
            if buf:
                chunks.append(buf)
                buf = ""
            chunks.append(para[:size])
            para = para[size - overlap :]
        if len(buf) + len(para) + 2 <= size:
            buf = f"{buf}\n\n{para}" if buf else para
        else:
            if buf:
                chunks.append(buf)
            tail = buf[-overlap:] if buf and overlap else ""
            buf = f"{tail}\n\n{para}".strip() if tail else para
    if buf:
        chunks.append(buf)
    return chunks


# ---------------------------------------------------------------- vector index
@dataclass
class SearchHit:
    text: str
    doc_id: int
    doc_title: str
    score: float


class VectorIndex:
    """In-memory cosine index over all chunks; rebuilt lazily after changes."""

    def __init__(self):
        self._lock = threading.Lock()
        self._dirty = True
        self._matrix = np.zeros((0, EMBED_DIM), dtype=np.float32)
        self._meta: list[tuple[str, int, str]] = []

    def invalidate(self) -> None:
        self._dirty = True

    def _rebuild(self) -> None:
        with session_scope() as s:
            rows = (
                s.query(KnowledgeChunk.text, KnowledgeChunk.embedding, KnowledgeDoc.id, KnowledgeDoc.title)
                .join(KnowledgeDoc, KnowledgeDoc.id == KnowledgeChunk.doc_id)
                .all()
            )
        if rows:
            self._matrix = np.vstack([np.frombuffer(r[1], dtype=np.float32) for r in rows])
        else:
            self._matrix = np.zeros((0, EMBED_DIM), dtype=np.float32)
        self._meta = [(r[0], r[2], r[3]) for r in rows]
        self._dirty = False

    def search_vector(self, qvec: np.ndarray, k: int = 5) -> list[SearchHit]:
        with self._lock:
            if self._dirty:
                self._rebuild()
            if self._matrix.shape[0] == 0:
                return []
            scores = self._matrix @ qvec.astype(np.float32)
            top = np.argsort(-scores)[:k]
            return [
                SearchHit(text=self._meta[i][0], doc_id=self._meta[i][1], doc_title=self._meta[i][2], score=float(scores[i]))
                for i in top
            ]

    def size(self) -> int:
        with self._lock:
            if self._dirty:
                self._rebuild()
            return self._matrix.shape[0]


index = VectorIndex()


# ---------------------------------------------------------------- public API
async def add_document(title: str, text: str, *, source: str = "", kind: str = "text") -> KnowledgeDoc:
    chunks = chunk_text(text)
    if not chunks:
        raise ValueError("Hujjatda matn topilmadi")
    llm = runtime.require_llm()
    # Prefix chunks with the title so retrieval keeps document context
    vectors = await llm.embed([f"{title}\n{c}" for c in chunks])

    def _save() -> KnowledgeDoc:
        with session_scope() as s:
            doc = KnowledgeDoc(title=title[:500], source=source[:1000], kind=kind, chunk_count=len(chunks), char_count=len(text))
            s.add(doc)
            s.flush()
            for c, v in zip(chunks, vectors):
                s.add(KnowledgeChunk(doc_id=doc.id, text=c, embedding=v.astype(np.float32).tobytes()))
            return doc

    doc = await asyncio.to_thread(_save)
    index.invalidate()
    log_activity("knowledge", f"Bazaga qo'shildi: «{title}» ({len(chunks)} bo'lak)")
    return doc


async def add_file(filename: str, data: bytes) -> KnowledgeDoc:
    text = await asyncio.to_thread(extract_text, filename, data)
    return await add_document(Path(filename).stem, text, source=filename, kind="file")


async def add_url(url: str) -> KnowledgeDoc:
    title, text = await fetch_url_text(url)
    return await add_document(title, text, source=url, kind="url")


def delete_document(doc_id: int) -> bool:
    with session_scope() as s:
        doc = s.get(KnowledgeDoc, doc_id)
        if not doc:
            return False
        s.query(KnowledgeChunk).filter(KnowledgeChunk.doc_id == doc_id).delete()
        s.delete(doc)
    index.invalidate()
    log_activity("knowledge", f"Bazadan o'chirildi: #{doc_id}")
    return True


async def search(query: str, k: int = 5) -> list[SearchHit]:
    if not query.strip() or index.size() == 0:
        return []
    llm = runtime.require_llm()
    qvec = (await llm.embed([query], query=True))[0]
    return index.search_vector(qvec, k)
