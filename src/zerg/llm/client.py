"""LLM client — unified provider support via litellm."""

import logging

import httpx
import litellm

from zerg.config import LLMConfig

# Silence litellm's verbose logging
litellm.suppress_debug_info = True
logging.getLogger("LiteLLM").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


class LLMClient:
    """Async LLM client supporting Ollama, Anthropic, OpenAI, and others."""

    def __init__(self, config: LLMConfig):
        self._config = config

        # Build litellm model identifier
        if config.provider == "ollama":
            self._model = f"ollama/{config.model}"
        elif config.provider == "openai":
            self._model = config.model
        else:
            self._model = f"{config.provider}/{config.model}"

    @property
    def provider(self) -> str:
        return self._config.provider

    @property
    def model(self) -> str:
        return self._config.model

    async def chat(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        """Send a chat completion request via litellm."""
        kwargs: dict = {
            "model": self._model,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools

        # Provider-specific config
        if self._config.provider == "ollama":
            base = self._config.base_url
            # litellm expects base URL without /v1 for Ollama
            if base.endswith("/v1"):
                base = base[:-3]
            kwargs["api_base"] = base

        if self._config.api_key:
            kwargs["api_key"] = self._config.api_key

        response = await litellm.acompletion(**kwargs)
        return response.model_dump()

    async def health(self) -> bool:
        """Check if the LLM service is reachable."""
        if self._config.provider == "ollama":
            try:
                async with httpx.AsyncClient(
                    base_url=self._config.base_url, timeout=5.0
                ) as client:
                    response = await client.get("/models")
                    return response.status_code == 200
            except httpx.HTTPError:
                return False
        else:
            # Cloud providers — healthy if api_key is configured
            return bool(self._config.api_key)

    async def close(self):
        pass  # litellm manages connections internally
