"""Model pool — lazy cache of LLMClient instances, one per configured model."""

from __future__ import annotations

import logging

from hive.config import ModelEntry
from hive.llm.client import LLMClient

logger = logging.getLogger(__name__)


class ModelPool:
    """Caches one LLMClient per model ID. Thread-safe under asyncio (single-threaded)."""

    def __init__(self, models: list[ModelEntry]):
        self._entries: dict[str, ModelEntry] = {m.id: m for m in models}
        self._clients: dict[str, LLMClient] = {}

    def get(self, model_id: str) -> LLMClient | None:
        """Get or lazily create a client for a configured model."""
        if client := self._clients.get(model_id):
            return client
        entry = self._entries.get(model_id)
        if not entry:
            return None
        client = LLMClient(entry)
        self._clients[model_id] = client
        return client

    def get_or_create(self, model_id: str, entry: ModelEntry) -> LLMClient:
        """Get cached client or create from an ad-hoc entry (e.g. Ollama auto-discovered)."""
        if client := self._clients.get(model_id):
            return client
        self._entries[model_id] = entry
        client = LLMClient(entry)
        self._clients[model_id] = client
        return client

    @property
    def default_id(self) -> str | None:
        """ID of the first configured model (used as default for new connections)."""
        return next(iter(self._entries), None)

    def entries(self) -> list[ModelEntry]:
        """All configured model entries."""
        return list(self._entries.values())
