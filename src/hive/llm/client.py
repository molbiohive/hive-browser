"""LLM client — unified provider support via litellm."""

import json
import logging

import httpx
import litellm

from hive.config import ModelEntry

# Silence litellm's verbose logging
litellm.suppress_debug_info = True
logging.getLogger("LiteLLM").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)
_dump = logging.getLogger("hive.llm.dump")


class LLMClient:
    """Async LLM client supporting Ollama, Anthropic, OpenAI, and others."""

    def __init__(self, config: ModelEntry):
        self._config = config

        # Build litellm model identifier — litellm always needs provider/ prefix
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
            base = self._config.base_url or "http://localhost:11434"
            # litellm expects base URL without /v1 for Ollama
            if base.endswith("/v1"):
                base = base[:-3]
            kwargs["api_base"] = base
        elif self._config.base_url:
            # Custom endpoint (vLLM, etc.) — pass base URL to litellm
            kwargs["api_base"] = self._config.base_url

        if self._config.api_key:
            kwargs["api_key"] = self._config.api_key
        elif self._config.provider == "openai" and self._config.base_url:
            # Local OpenAI-compatible endpoints (vLLM, etc.) don't need a real key
            # but litellm requires one to be set
            kwargs["api_key"] = "no-key"

        kwargs["timeout"] = 120  # seconds — prevent indefinite hangs
        kwargs["max_tokens"] = self._config.max_tokens

        # vLLM + thinking models (Qwen3): disable thinking for tool-calling turns
        # to prevent unbounded <think> tokens consuming the KV cache budget
        if self._config.base_url and tools:
            kwargs.setdefault("extra_body", {})
            kwargs["extra_body"]["chat_template_kwargs"] = {"enable_thinking": False}

        if _dump.isEnabledFor(logging.DEBUG):
            _dump.debug(json.dumps({
                "dir": "request",
                "model": self._model,
                "messages": messages,
                "tools": [t["function"]["name"] for t in tools] if tools else None,
                "tool_choice": tool_choice,
            }, default=str))

        response = await litellm.acompletion(**kwargs)
        try:
            result = response.model_dump()
        except Exception:
            # litellm Pydantic may reject unknown finish_reason (e.g. "refusal")
            result = _extract_response(response)

        if _dump.isEnabledFor(logging.DEBUG):
            _dump.debug(json.dumps({
                "dir": "response",
                "model": self._model,
                "usage": result.get("usage"),
                "choices": result.get("choices"),
            }, default=str))

        return result

    async def health(self) -> bool:
        """Check if the LLM service is reachable."""
        if self._config.base_url:
            # Local providers (Ollama, vLLM, etc.) — ping the endpoint
            try:
                base = self._config.base_url.rstrip("/")
                if not base.endswith("/v1"):
                    base += "/v1"
                async with httpx.AsyncClient(
                    base_url=base, timeout=5.0
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
