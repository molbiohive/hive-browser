"""LLM client — unified provider support via litellm."""

import logging

import httpx
import litellm

from hive.config import ModelEntry

# Silence litellm's verbose logging
litellm.suppress_debug_info = True
logging.getLogger("LiteLLM").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


class LLMClient:
    """Async LLM client supporting Ollama, Anthropic, OpenAI, and others."""

    def __init__(self, config: ModelEntry):
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

    @property
    def base_url(self) -> str:
        return self._config.base_url

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        tool_choice: str | None = None,
    ) -> dict:
        """Send a chat completion request via litellm."""
        kwargs: dict = {
            "model": self._model,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools
            if tool_choice:
                kwargs["tool_choice"] = tool_choice

        # Provider-specific config
        if self._config.provider == "ollama":
            base = self._config.base_url
            # litellm expects base URL without /v1 for Ollama
            if base.endswith("/v1"):
                base = base[:-3]
            kwargs["api_base"] = base

        if self._config.api_key:
            kwargs["api_key"] = self._config.api_key

        kwargs["timeout"] = 120  # seconds — prevent indefinite hangs

        response = await litellm.acompletion(**kwargs)
        try:
            return response.model_dump()
        except Exception:
            # litellm Pydantic may reject unknown finish_reason (e.g. "refusal")
            return _extract_response(response)

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


def _extract_response(response) -> dict:
    """Manual extraction when model_dump() fails on unknown fields."""
    choice = response.choices[0] if response.choices else None
    msg = getattr(choice, "message", None)
    content = getattr(msg, "content", None) or ""
    tool_calls_raw = getattr(msg, "tool_calls", None)
    finish = getattr(choice, "finish_reason", "stop") or "stop"
    usage = getattr(response, "usage", None)

    message: dict = {"role": "assistant", "content": content}
    if tool_calls_raw:
        message["tool_calls"] = [
            {
                "id": getattr(tc, "id", ""),
                "type": "function",
                "function": {
                    "name": getattr(tc.function, "name", ""),
                    "arguments": getattr(tc.function, "arguments", "{}"),
                },
            }
            for tc in tool_calls_raw
        ]

    return {
        "choices": [{"message": message, "finish_reason": finish}],
        "usage": {
            "prompt_tokens": getattr(usage, "prompt_tokens", 0) if usage else 0,
            "completion_tokens": getattr(usage, "completion_tokens", 0) if usage else 0,
        },
    }
