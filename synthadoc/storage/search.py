# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import aiosqlite
from rank_bm25 import BM25Okapi

from synthadoc.storage.wiki import WikiStorage


@dataclass
class SearchResult:
    slug: str
    score: float
    title: str
    snippet: str


class VectorStore:
    """SQLite-backed store for page embeddings (float32 blobs)."""

    def __init__(self, db_path: Path) -> None:
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    async def init(self) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS embeddings (
                    slug       TEXT PRIMARY KEY,
                    embedding  BLOB NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)
            await db.commit()

    async def upsert(self, slug: str, embedding: list[float]) -> None:
        import numpy as np
        blob = np.array(embedding, dtype=np.float32).tobytes()
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO embeddings (slug, embedding, updated_at)"
                " VALUES (?, ?, datetime('now'))",
                (slug, blob),
            )
            await db.commit()

    async def get(self, slug: str) -> "Optional[list[float]]":
        import numpy as np
        async with aiosqlite.connect(self._path) as db:
            async with db.execute(
                "SELECT embedding FROM embeddings WHERE slug=?", (slug,)
            ) as cur:
                row = await cur.fetchone()
        if row is None:
            return None
        return np.frombuffer(row[0], dtype=np.float32).tolist()

    async def get_all(self) -> "dict[str, list[float]]":
        import numpy as np
        async with aiosqlite.connect(self._path) as db:
            async with db.execute("SELECT slug, embedding FROM embeddings") as cur:
                rows = await cur.fetchall()
        return {r[0]: np.frombuffer(r[1], dtype=np.float32).tolist() for r in rows}

    async def list_slugs(self) -> list[str]:
        async with aiosqlite.connect(self._path) as db:
            async with db.execute("SELECT slug FROM embeddings") as cur:
                rows = await cur.fetchall()
        return [r[0] for r in rows]

    async def count(self) -> int:
        async with aiosqlite.connect(self._path) as db:
            async with db.execute("SELECT COUNT(*) FROM embeddings") as cur:
                row = await cur.fetchone()
        return row[0] if row else 0


_EMBED_MODEL_NAME = "BAAI/bge-small-en-v1.5"


class HybridSearch:
    """BM25 full-text search with optional vector re-ranking via fastembed."""

    def __init__(self, store: WikiStorage, index_path: Path,
                 search_cfg=None) -> None:
        self._store = store
        self._index_path = index_path
        self._cached_corpus: Optional[tuple[list[str], list[list[str]]]] = None
        self._search_cfg = search_cfg      # SearchConfig or None
        self._vector_store: Optional[VectorStore] = None
        self._embed_model = None            # lazy loaded

    def _vector_enabled(self) -> bool:
        return self._search_cfg is not None and self._search_cfg.vector

    async def init_vector(self) -> None:
        """Create embeddings.db table. Call from orchestrator when vector=true."""
        if not self._vector_enabled():
            return
        try:
            from fastembed import TextEmbedding  # noqa: F401
        except ImportError:
            raise ImportError(
                "fastembed is required for vector search. "
                "Run: pip install fastembed  then restart the server."
            )
        self._vector_store = VectorStore(self._index_path)
        await self._vector_store.init()

    def _get_embed_model(self):
        if self._embed_model is None:
            try:
                from fastembed import TextEmbedding
            except ImportError:
                raise ImportError(
                    "fastembed is required for vector search. "
                    "Install with: pip install fastembed"
                )
            self._embed_model = TextEmbedding(_EMBED_MODEL_NAME)
        return self._embed_model

    def _embed_text(self, text: str) -> list[float]:
        model = self._get_embed_model()
        result = list(model.embed([text[:512]]))
        return result[0].tolist()

    async def embed_page(self, slug: str, text: str) -> None:
        """Embed a page and persist in embeddings.db. No-op when vector disabled."""
        if not self._vector_enabled() or self._vector_store is None:
            return
        loop = asyncio.get_running_loop()
        embedding = await loop.run_in_executor(None, self._embed_text, text)
        await self._vector_store.upsert(slug, embedding)

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        ascii_tokens = re.findall(r"[a-z0-9]+", text.lower())
        cjk_tokens = re.findall(
            r"[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]", text
        )
        return ascii_tokens + cjk_tokens

    def invalidate_index(self) -> None:
        """Drop the in-memory corpus cache. Call after any page write."""
        self._cached_corpus = None

    def _corpus(self) -> tuple[list[str], list[list[str]]]:
        if self._cached_corpus is not None:
            return self._cached_corpus
        slugs = self._store.list_pages()
        tokenized = []
        for slug in slugs:
            page = self._store.read_page(slug)
            text = f"{page.title} {' '.join(page.tags)} {page.content}" if page else ""
            tokenized.append(self._tokenize(text))
        self._cached_corpus = (slugs, tokenized)
        return self._cached_corpus

    def bm25_search(self, query_terms: list[str], top_n: int = 10,
                    scoped_slugs: list[str] | None = None) -> list[SearchResult]:
        slugs, corpus = self._corpus()
        if not corpus:
            return []
        if scoped_slugs is not None:
            scoped_set = set(scoped_slugs)
            pairs = [(s, t) for s, t in zip(slugs, corpus) if s in scoped_set]
            if not pairs:
                return []
            slugs = [p[0] for p in pairs]
            corpus = [p[1] for p in pairs]
        bm25 = BM25Okapi(corpus)
        scores = bm25.get_scores(self._tokenize(" ".join(query_terms)))
        ranked = sorted(zip(slugs, scores), key=lambda x: x[1], reverse=True)
        results = []
        for slug, score in ranked[:top_n]:
            if score <= 0:
                continue
            page = self._store.read_page(slug)
            snippet = (page.content[:120] + "...") if page and len(page.content) > 120 \
                      else (page.content if page else "")
            results.append(SearchResult(
                slug=slug, score=float(score),
                title=page.title if page else slug,
                snippet=snippet,
            ))
        return results

    async def hybrid_search(self, query_terms: list[str],
                            top_n: int = 10,
                            scoped_slugs: list[str] | None = None) -> list[SearchResult]:
        """BM25 fetch + vector cosine re-rank when enabled; BM25-only otherwise."""
        top_candidates = (
            self._search_cfg.vector_top_candidates
            if self._vector_enabled() and self._search_cfg
            else top_n
        )
        candidates = self.bm25_search(query_terms, top_n=top_candidates, scoped_slugs=scoped_slugs)

        if not self._vector_enabled() or self._vector_store is None or not candidates:
            return candidates[:top_n]

        import numpy as np
        stored = await self._vector_store.get_all()
        if not stored:
            return candidates[:top_n]

        query_text = " ".join(query_terms)
        loop = asyncio.get_running_loop()
        query_emb = await loop.run_in_executor(None, self._embed_text, query_text)
        q_arr = np.array(query_emb, dtype=np.float32)
        q_norm = np.linalg.norm(q_arr)

        reranked = []
        for r in candidates:
            page_emb = stored.get(r.slug)
            if page_emb is None:
                reranked.append((r, 0.0))
                continue
            p_arr = np.array(page_emb, dtype=np.float32)
            norm = q_norm * np.linalg.norm(p_arr)
            cos_sim = float(np.dot(q_arr, p_arr) / norm) if norm > 0 else 0.0
            reranked.append((r, cos_sim))

        reranked.sort(key=lambda x: x[1], reverse=True)
        return [r for r, _ in reranked[:top_n]]
