"""LLM provider abstraction — LM Studio + Ollama via OpenAI-compatible API.

Sprint 17: fallback cascade + circuit breaker. If a slot fails (0 tokens,
HTTP error, timeout), the system automatically tries the next slot in the
chain (summariser → reporter → inference). A per-slot circuit breaker
avoids wasting latency on a slot that has failed repeatedly.
"""

import asyncio
import logging
import time
from typing import Any, AsyncIterator

import httpx

from src.core.config import config

logger = logging.getLogger("backend.llm")

# ---------------------------------------------------------------------------
# Slot resolution helpers (used by polling, evidence_processor, compressor)
# ---------------------------------------------------------------------------


def slot_settings(settings: dict[str, Any], slot: str) -> dict[str, Any]:
    """Resolve LLM settings for a given slot, with fallback to inference.

    Returns {provider, model, temperature, max_tokens, num_ctx, _slot_name}.
    """
    provider = settings.get(f"{slot}_provider") or settings.get("inference_provider")
    model = settings.get(f"{slot}_model") or settings.get("inference_model")
    temperature = settings.get(f"{slot}_temperature")
    if temperature is None:
        temperature = settings.get("inference_temperature", 0.7)
    max_tokens = settings.get(f"{slot}_max_tokens")
    if max_tokens is None:
        max_tokens = settings.get("inference_max_tokens", 2048)
    num_ctx = settings.get(f"{slot}_num_ctx")
    if num_ctx is None:
        num_ctx = settings.get("inference_num_ctx")
    return {
        "provider": provider,
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "num_ctx": num_ctx if provider == "ollama" else None,
        "_slot_name": slot,
    }


# Fallback chains by primary slot role.
_FALLBACK_CHAINS: dict[str, list[str]] = {
    "summariser": ["summariser", "reporter", "inference"],
    "reporter": ["reporter", "inference"],
    "inference": ["inference"],
}


def build_fallback_chain(settings: dict[str, Any], primary_slot: str) -> list[dict[str, Any]]:
    """Build a list of slot configs to try in order (primary → fallbacks).

    Deduplicates slots that resolve to the same provider:model (e.g. if
    reporter and inference point to the same model, only try once).
    """
    slot_names = _FALLBACK_CHAINS.get(primary_slot, [primary_slot])
    configs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for name in slot_names:
        cfg = slot_settings(settings, name)
        key = f"{cfg['provider']}:{cfg['model']}"
        if key in seen:
            continue
        seen.add(key)
        configs.append(cfg)
    return configs


class LLMProvider:
    """Unified interface for LM Studio and Ollama inference."""

    # Circuit breaker constants
    _CB_THRESHOLD = 3       # failures before marking slot as down
    _CB_WINDOW = 60.0       # seconds — only count recent failures
    _CB_COOLDOWN = 300.0    # seconds — how long a down slot stays down

    def __init__(self):
        self._active_provider: str | None = None
        self._slot_failures: dict[str, list[float]] = {}
        # Track which fallback was last used, for email notifications
        self.last_fallback_event: dict[str, Any] | None = None

    # --- Circuit breaker ---

    def _slot_key(self, provider: str, model: str) -> str:
        return f"{provider}:{model}"

    def is_slot_down(self, provider: str, model: str) -> bool:
        """Check if a slot is tripped by the circuit breaker."""
        key = self._slot_key(provider, model)
        failures = self._slot_failures.get(key, [])
        now = time.time()
        recent = [t for t in failures if now - t < self._CB_WINDOW]
        self._slot_failures[key] = recent
        if len(recent) >= self._CB_THRESHOLD:
            if now - recent[-1] < self._CB_COOLDOWN:
                return True
            # Cooldown expired — give it another chance
            self._slot_failures[key] = []
        return False

    def _mark_failure(self, provider: str, model: str):
        key = self._slot_key(provider, model)
        self._slot_failures.setdefault(key, []).append(time.time())

    def _mark_success(self, provider: str, model: str):
        key = self._slot_key(provider, model)
        self._slot_failures.pop(key, None)

    def get_slot_health(self) -> dict[str, str]:
        """Return per-slot health: {\"provider:model\": \"online\"|\"down\"}."""
        result: dict[str, str] = {}
        now = time.time()
        for key, failures in list(self._slot_failures.items()):
            recent = [t for t in failures if now - t < self._CB_WINDOW]
            if len(recent) >= self._CB_THRESHOLD and now - recent[-1] < self._CB_COOLDOWN:
                result[key] = "down"
            elif recent:
                result[key] = "degraded"
            # no entry → online (caller infers online for missing keys)
        return result

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
        messages: list[dict[str, Any]],
        provider: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        num_ctx: int | None = None,
    ) -> AsyncIterator[str]:
        """Stream chat completion tokens. Tries LM Studio first, then Ollama.

        Yields individual tokens as strings.

        `messages` follows the OpenAI chat format. `content` may be either a plain
        string OR a list of content parts for multimodal input, e.g.:
            [{"type": "text", "text": "..."},
             {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}}]
        Both LM Studio and Ollama accept this via /v1/chat/completions when the
        underlying model is vision-capable.
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

        tokens_yielded = 0
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
                            tokens_yielded += 1
                            yield token
                    except (ValueError, KeyError, IndexError):
                        continue
        # Sprint 16 hotfix: if the stream completed cleanly with zero tokens,
        # the model was probably evicted from LM Studio or crashed silently.
        # Surface this in the logs so we can diagnose it without digging.
        if tokens_yielded == 0:
            logger.warning(
                f"stream_chat produced ZERO tokens — model={model} provider={provider}. "
                f"Likely model eviction, context overflow, or empty <think> block."
            )

    async def chat(
        self,
        messages: list[dict[str, Any]],
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

    # --- Fallback cascade (Sprint 17) ---

    async def stream_chat_with_fallback(
        self,
        messages: list[dict[str, Any]],
        slot_configs: list[dict[str, Any]],
    ) -> AsyncIterator[str]:
        """Stream tokens, trying each slot config in order until one succeeds.

        Yields tokens from the first slot that produces a non-empty response.
        If a slot yields 0 tokens or raises, it is marked as failed in the
        circuit breaker and the next slot in the chain is tried. If all slots
        fail, the last exception is re-raised.

        ``slot_configs`` is a list of dicts with keys:
            provider, model, temperature, max_tokens, num_ctx, _slot_name
        Typically built via ``build_fallback_chain(settings, primary_slot)``.
        """
        last_error: Exception | None = None

        for i, cfg in enumerate(slot_configs):
            provider = cfg.get("provider", "")
            model = cfg.get("model", "")
            slot_name = cfg.get("_slot_name", f"slot-{i}")

            if self.is_slot_down(provider, model):
                logger.info(f"Skipping {slot_name} ({provider}/{model}) — circuit breaker open")
                continue

            try:
                tokens_yielded = 0
                async for token in self.stream_chat(
                    messages=messages,
                    provider=provider,
                    model=model,
                    temperature=cfg.get("temperature", 0.7),
                    max_tokens=cfg.get("max_tokens", 2048),
                    num_ctx=cfg.get("num_ctx"),
                ):
                    tokens_yielded += 1
                    yield token

                if tokens_yielded == 0:
                    raise RuntimeError(f"Zero tokens from {provider}/{model}")

                # Success
                self._mark_success(provider, model)
                if i > 0:
                    failed_p = slot_configs[0].get("provider", "")
                    failed_m = slot_configs[0].get("model", "")
                    logger.warning(
                        f"{slot_name} served by fallback #{i}: {provider}/{model}"
                    )
                    self.last_fallback_event = {
                        "slot": slot_name,
                        "failed_provider": failed_p,
                        "failed_model": failed_m,
                        "fallback_provider": provider,
                        "fallback_model": model,
                        "timestamp": time.time(),
                    }
                    # Sprint 17: notify admin that slot degraded
                    asyncio.create_task(self._notify_slot_event(
                        slot_name, failed_p, failed_m,
                        str(last_error or "unknown"),
                        fallback_provider=provider,
                        fallback_model=model,
                    ))
                return

            except Exception as e:
                self._mark_failure(provider, model)
                last_error = e
                if i < len(slot_configs) - 1:
                    next_cfg = slot_configs[i + 1]
                    logger.warning(
                        f"{slot_name} ({provider}/{model}) failed: {e}. "
                        f"Falling back to {next_cfg.get('_slot_name', next_cfg.get('model'))}"
                    )
                else:
                    logger.error(
                        f"{slot_name} ({provider}/{model}) failed: {e}. "
                        f"No more fallbacks."
                    )

        # All slots failed — notify admin (offline, no fallback)
        if slot_configs:
            first = slot_configs[0]
            asyncio.create_task(self._notify_slot_event(
                first.get("_slot_name", "unknown"),
                first.get("provider", ""),
                first.get("model", ""),
                str(last_error or "all slots exhausted"),
            ))

        if last_error:
            raise last_error
        raise RuntimeError("No LLM slots available (all circuit breakers open)")

    async def _notify_slot_event(
        self,
        slot_name: str,
        failed_provider: str,
        failed_model: str,
        error: str,
        fallback_provider: str | None = None,
        fallback_model: str | None = None,
    ):
        """Fire-and-forget email notification for slot failures."""
        try:
            from src.services.smtp_service import notify_slot_failure
            await notify_slot_failure(
                slot_name=slot_name,
                failed_provider=failed_provider,
                failed_model=failed_model,
                error=error,
                fallback_provider=fallback_provider,
                fallback_model=fallback_model,
            )
        except Exception as e:
            logger.debug(f"Slot failure notification skipped: {e}")

    async def chat_with_fallback(
        self,
        messages: list[dict[str, Any]],
        slot_configs: list[dict[str, Any]],
    ) -> str:
        """Non-streaming chat with fallback cascade. Returns full response."""
        full_response = ""
        async for token in self.stream_chat_with_fallback(messages, slot_configs):
            full_response += token
        return full_response


# Singleton
llm = LLMProvider()
