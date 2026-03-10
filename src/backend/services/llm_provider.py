"""LLM provider abstraction — LM Studio + Ollama via OpenAI-compatible API."""

import logging
from typing import Any, AsyncIterator

import httpx

from src.core.config import config

logger = logging.getLogger("backend.llm")


class LLMProvider:
    """Unified interface for LM Studio and Ollama inference."""

    def __init__(self):
        self._active_provider: str | None = None

    # --- Health Checks (lesson #3: always try-except) ---

    async def check_lm_studio(self) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{config.lm_studio_endpoint}/models")
                resp.raise_for_status()
                data = resp.json()
                models = [m["id"] for m in data.get("data", [])]
                return {"status": "online", "models": models}
        except Exception as e:
            return {"status": "offline", "error": str(e), "models": []}

    async def check_ollama(self) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{config.ollama_endpoint}/api/tags")
                resp.raise_for_status()
                data = resp.json()
                models = [m["name"] for m in data.get("models", [])]
                return {"status": "online", "models": models}
        except Exception as e:
            return {"status": "offline", "error": str(e), "models": []}

    async def check_health(self) -> dict[str, Any]:
        """Check both providers and return combined status."""
        lm = await self.check_lm_studio()
        ol = await self.check_ollama()
        return {"lm_studio": lm, "ollama": ol}

    # --- Inference ---

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        provider: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        num_ctx: int | None = None,
    ) -> AsyncIterator[str]:
        """Stream chat completion tokens. Tries LM Studio first, then Ollama.

        Yields individual tokens as strings.
        """
        # Determine provider and model
        if provider == "ollama":
            endpoint = f"{config.ollama_endpoint}/v1"
            model = model or config.ollama_summariser_model
        elif provider == "lm_studio":
            endpoint = config.lm_studio_endpoint
            model = model or config.lm_studio_model
        else:
            # Auto-detect: try LM Studio first
            lm_health = await self.check_lm_studio()
            if lm_health["status"] == "online":
                endpoint = config.lm_studio_endpoint
                model = model or config.lm_studio_model
                provider = "lm_studio"
            else:
                ol_health = await self.check_ollama()
                if ol_health["status"] == "online":
                    endpoint = f"{config.ollama_endpoint}/v1"
                    model = model or config.ollama_summariser_model
                    provider = "ollama"
                else:
                    raise ConnectionError("No LLM provider available")

        self._active_provider = provider
        logger.info(f"Using {provider} with model {model}")

        # Build request body — OpenAI-compatible for both providers
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }

        # Ollama supports num_ctx via options
        if provider == "ollama" and num_ctx:
            body["options"] = {"num_ctx": num_ctx}

        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=10.0)) as client:
            async with client.stream(
                "POST",
                f"{endpoint}/chat/completions",
                json=body,
                headers={"Content-Type": "application/json"},
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    payload = line[6:]
                    if payload.strip() == "[DONE]":
                        break
                    try:
                        import json
                        chunk = json.loads(payload)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        token = delta.get("content")
                        if token:
                            yield token
                    except (ValueError, KeyError, IndexError):
                        continue

    async def chat(
        self,
        messages: list[dict[str, str]],
        provider: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> str:
        """Non-streaming chat completion. Returns full response."""
        full_response = ""
        async for token in self.stream_chat(
            messages, provider=provider, model=model,
            temperature=temperature, max_tokens=max_tokens,
        ):
            full_response += token
        return full_response


# Singleton
llm = LLMProvider()
