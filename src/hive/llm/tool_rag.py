"""RAG tool selection — picks relevant tools for the agent loop.

Supports two backends:
- TF-IDF (pure Python, zero deps) — default fallback
- litellm embeddings — when an embedding model is configured
"""

from __future__ import annotations

import logging
import math
import re
from typing import TYPE_CHECKING, Any

from hive.llm.prompts import build_plan_messages, build_tool_catalog

if TYPE_CHECKING:
    from hive.llm.client import LLMClient
    from hive.tools.base import Tool

logger = logging.getLogger(__name__)


# ── TF-IDF helpers (pure Python, zero deps) ──

_SPLIT = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    """Lowercase split on non-alphanumeric."""
    return _SPLIT.findall(text.lower())


def _build_tfidf(docs: list[list[str]]) -> dict[str, float]:
    """Build IDF weights from tokenized documents."""
    n = len(docs)
    idf: dict[str, float] = {}
    doc_sets = [set(doc) for doc in docs]
    vocab: set[str] = set()
    for s in doc_sets:
        vocab.update(s)
    for term in vocab:
        df = sum(1 for s in doc_sets if term in s)
        idf[term] = math.log((n + 1) / (df + 1)) + 1  # smoothed IDF
    return idf


def _tfidf_vector(tokens: list[str], idf: dict[str, float]) -> dict[str, float]:
    """Compute TF-IDF vector as a sparse dict."""
    tf: dict[str, int] = {}
    for t in tokens:
        tf[t] = tf.get(t, 0) + 1
    return {term: count * idf[term] for term, count in tf.items() if term in idf}


def _cosine_sim(a: dict[str, float], b: dict[str, float]) -> float:
    """Cosine similarity between two sparse vectors."""
    dot = sum(a.get(k, 0) * b.get(k, 0) for k in set(a) | set(b))
    norm_a = math.sqrt(sum(v * v for v in a.values())) or 1e-9
    norm_b = math.sqrt(sum(v * v for v in b.values())) or 1e-9
    return dot / (norm_a * norm_b)


def _cosine_dense(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two dense vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a)) or 1e-9
    norm_b = math.sqrt(sum(x * x for x in b)) or 1e-9
    return dot / (norm_a * norm_b)


# ── ToolRAG ──


class ToolRAG:
    """Planning + RAG tool selector.

    1. plan() — cheap LLM call with catalog only (no schemas)
    2. select() — cosine similarity picks relevant tools
    """

    def __init__(
        self,
        tools: list[Tool],
        embedding_model: str = "",
        embedding_base_url: str = "",
        threshold: float = 0.3,
        top_k: int = 8,
    ):
        self._tools = list(tools)
        self._embedding_model = embedding_model
        self._embedding_base_url = embedding_base_url
        self._threshold = threshold
        self._top_k = top_k

        # Precompute catalog text
        self._catalog = build_tool_catalog(self._tools)

        # Lazy-init TF-IDF fields
        self._tfidf_ready = False
        self._idf: dict[str, float] = {}
        self._tool_vecs: list[dict[str, float]] = []

        # Lazy-init embedding cache (litellm path)
        self._embedding_vecs: list[list[float]] | None = None

        backend = embedding_model or "tfidf"
        logger.info(
            "ToolRAG initialized (%d tools, model=%s, threshold=%.2f, top_k=%d)",
            len(self._tools), backend, threshold, top_k,
        )

    # ── Planning ──

    async def plan(
        self,
        user_input: str,
        llm_client: LLMClient,
        history: list[dict] | None = None,
    ) -> tuple[str, str, dict[str, int]]:
        """Run the planning call. Returns (prefix, content, usage_dict).

        prefix is "ACTION" or "ANSWER".
        """
        messages = build_plan_messages(self._catalog, user_input, history)
        response = await llm_client.chat(messages)

        usage = response.get("usage") or {}
        usage_dict = {
            "in": usage.get("prompt_tokens", 0),
            "out": usage.get("completion_tokens", 0),
        }

        raw = (response["choices"][0]["message"].get("content") or "").strip()

        # Parse prefix
        if raw.upper().startswith("ANSWER:"):
            return "ANSWER", raw[7:].strip(), usage_dict
        if raw.upper().startswith("ACTION:"):
            return "ACTION", raw[7:].strip(), usage_dict
        # Missing prefix — default to ACTION (safer: will trigger RAG)
        logger.debug("Planning response missing prefix, defaulting to ACTION: %s", raw[:80])
        return "ACTION", raw, usage_dict

    # ── RAG Selection ──

    async def select(self, plan_text: str) -> list[Tool]:
        """Select tools relevant to the plan text via cosine similarity."""
        if self._embedding_model:
            return await self._select_embedding(plan_text)
        return self._select_tfidf(plan_text)

    def _ensure_tfidf(self):
        """Lazy-build TF-IDF index from tool descriptions."""
        if self._tfidf_ready:
            return
        tool_docs = [_tokenize(f"{t.name} {t.description}") for t in self._tools]
        self._idf = _build_tfidf(tool_docs)
        self._tool_vecs = [_tfidf_vector(doc, self._idf) for doc in tool_docs]
        self._tfidf_ready = True

    def _select_tfidf(self, plan_text: str) -> list[Tool]:
        """Select tools using TF-IDF cosine similarity."""
        self._ensure_tfidf()
        query_vec = _tfidf_vector(_tokenize(plan_text), self._idf)

        scored = sorted(
            ((i, _cosine_sim(query_vec, tv)) for i, tv in enumerate(self._tool_vecs)),
            key=lambda x: -x[1],
        )

        selected: list[Tool] = []
        for idx, sim in scored:
            if len(selected) >= self._top_k:
                break
            if sim >= self._threshold or len(selected) < 3:
                selected.append(self._tools[idx])
        return selected

    async def _select_embedding(self, plan_text: str) -> list[Tool]:
        """Select tools using litellm embeddings."""
        import litellm

        # Lazy-build tool embeddings
        if self._embedding_vecs is None:
            texts = [f"{t.name}: {t.description}" for t in self._tools]
            kwargs: dict[str, Any] = {"model": self._embedding_model, "input": texts}
            if self._embedding_base_url:
                kwargs["api_base"] = self._embedding_base_url
            resp = await litellm.aembedding(**kwargs)
            self._embedding_vecs = [item["embedding"] for item in resp.data]

        # Embed query
        kwargs = {"model": self._embedding_model, "input": [plan_text]}
        if self._embedding_base_url:
            kwargs["api_base"] = self._embedding_base_url
        resp = await litellm.aembedding(**kwargs)
        query_vec = resp.data[0]["embedding"]

        scored = sorted(
            ((i, _cosine_dense(query_vec, tv)) for i, tv in enumerate(self._embedding_vecs)),
            key=lambda x: -x[1],
        )

        selected: list[Tool] = []
        for idx, sim in scored:
            if len(selected) >= self._top_k:
                break
            if sim >= self._threshold or len(selected) < 3:
                selected.append(self._tools[idx])
        return selected
