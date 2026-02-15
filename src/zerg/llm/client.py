"""vLLM client — OpenAI-compatible API for tool calling and chat."""

import httpx

from zerg.config import LLMConfig


class LLMClient:
    """Async client for the vLLM OpenAI-compatible API."""

    def __init__(self, config: LLMConfig):
        self.base_url = config.base_url
        self.model = config.model
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=120.0)

    async def chat(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        """Send a chat completion request, optionally with tool schemas."""
        payload = {
            "model": self.model,
            "messages": messages,
        }
        if tools:
            payload["tools"] = tools

        response = await self._client.post("/chat/completions", json=payload)
        response.raise_for_status()
        return response.json()

    async def health(self) -> bool:
        """Check if the LLM service is reachable."""
        try:
            response = await self._client.get("/models")
            return response.status_code == 200
        except httpx.HTTPError:
            return False

    async def close(self):
        await self._client.aclose()
