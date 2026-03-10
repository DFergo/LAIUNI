import asyncio
import logging
from collections import deque
from typing import Any

import httpx

from src.services.frontend_registry import registry
from src.services.llm_provider import llm
from src.services.prompt_assembler import assemble_system_prompt
from src.services.rag_service import get_relevant_chunks
from src.services.session_store import store as history
from src.services.context_compressor import compress_if_needed, estimate_messages_tokens
from src.api.v1.admin.llm import get_llm_settings

logger = logging.getLogger("backend.polling")

# Processing queue — messages waiting for LLM
_processing_queue: deque[dict[str, Any]] = deque()
_processing_lock = asyncio.Lock()
_is_processing = False


async def poll_frontends():
    """Poll all enabled frontends for pending messages."""
    client = httpx.AsyncClient(timeout=10.0)
    enabled = registry.list_enabled()

    for frontend in enabled:
        url = frontend["url"]
        fid = frontend["id"]
        try:
            resp = await client.get(f"{url}/internal/queue")
            resp.raise_for_status()
            data = resp.json()
            messages = data.get("messages", [])
            registry.set_status(fid, "online")

            for msg in messages:
                msg["_frontend_url"] = url
                async with _processing_lock:
                    _processing_queue.append(msg)
                logger.info(f"Queued message {msg.get('message_id')} from {fid}")

        except Exception as e:
            registry.set_status(fid, "offline")
            logger.warning(f"Failed to poll {fid} ({url}): {e}")

    await client.aclose()


async def process_queue():
    """Process one message at a time from the queue (sequential — LLM is single-threaded)."""
    global _is_processing

    async with _processing_lock:
        if _is_processing or not _processing_queue:
            return
        _is_processing = True

    try:
        # Send queue position updates to all waiting messages
        await _send_queue_positions()

        while True:
            async with _processing_lock:
                if not _processing_queue:
                    break
                msg = _processing_queue.popleft()

            # Update positions for remaining messages
            await _send_queue_positions()

            await _safe_process(msg)
    finally:
        async with _processing_lock:
            _is_processing = False


async def _send_queue_positions():
    """Notify each queued session of their position."""
    async with _processing_lock:
        items = list(_processing_queue)

    client = httpx.AsyncClient(timeout=5.0)
    for i, msg in enumerate(items):
        url = msg.get("_frontend_url", "")
        token = msg.get("session_token", "")
        if url and token:
            try:
                await client.post(
                    f"{url}/internal/stream/{token}/chunk",
                    json={"event": "queue_position", "data": str(i + 1)},
                )
            except Exception:
                pass
    await client.aclose()


async def _safe_process(msg: dict[str, Any]):
    """Process a single message. Wrapped in try-except (lesson #2)."""
    frontend_url = msg.get("_frontend_url", "")
    session_token = msg.get("session_token", "")
    content = msg.get("content", "")
    survey = msg.get("survey")
    language = msg.get("language", "en")

    client = httpx.AsyncClient(timeout=30.0)
    try:
        # If first message with survey, build system prompt and store it
        if survey:
            system_prompt = assemble_system_prompt(survey, language)
            history.init_session(session_token, system_prompt, survey, language)

        # Add user message to history
        history.add_message(session_token, "user", content)

        # Build messages for LLM (system + conversation history)
        llm_messages = history.get_llm_messages(session_token)

        # Inject RAG context — retrieve relevant document chunks for this message
        rag_chunks = get_relevant_chunks(content)
        if rag_chunks:
            rag_context = (
                "The following excerpts from reference documents may be relevant "
                "to the user's message. Use them to ground your response where applicable. "
                "Cite the source if you reference specific provisions.\n\n"
                + "\n\n---\n\n".join(rag_chunks)
            )
            # Insert RAG context as a system message before the last user message
            llm_messages.insert(-1, {"role": "system", "content": rag_context})
            logger.debug(f"Injected {len(rag_chunks)} RAG chunks for session {session_token}")

        # Compress context if approaching limit (ADR-009)
        settings = get_llm_settings()
        context_tokens = estimate_messages_tokens(llm_messages)
        logger.info(f"[{session_token}] Context size: {context_tokens} tokens ({len(llm_messages)} messages)")
        llm_messages = await compress_if_needed(llm_messages, settings, session_token)

        # Try LLM inference, fall back to mock if unavailable
        raw_response = ""
        visible_response = ""
        in_think = False
        try:
            async for token in llm.stream_chat(
                messages=llm_messages,
                provider=settings.get("inference_provider"),
                model=settings.get("inference_model"),
                temperature=settings.get("inference_temperature", 0.7),
                max_tokens=settings.get("inference_max_tokens", 2048),
                num_ctx=settings.get("inference_num_ctx") if settings.get("inference_provider") == "ollama" else None,
            ):
                raw_response += token

                # Filter <think>...</think> blocks (Qwen3 reasoning tokens)
                if "<think>" in raw_response and not in_think:
                    in_think = True
                if in_think:
                    if "</think>" in raw_response:
                        in_think = False
                        # Skip everything up to after </think> + whitespace
                        after = raw_response.split("</think>", 1)[-1]
                        raw_response = after
                    continue

                # Stream visible tokens to frontend
                visible_response += token
                await client.post(
                    f"{frontend_url}/internal/stream/{session_token}/chunk",
                    json={"event": "token", "data": token},
                )
        except ConnectionError:
            # No LLM provider available — use mock response
            logger.warning(f"No LLM available for {session_token}, using mock")
            full_response = _mock_response(content)
            words = full_response.split(" ")
            for i, word in enumerate(words):
                t = word if i == 0 else " " + word
                await client.post(
                    f"{frontend_url}/internal/stream/{session_token}/chunk",
                    json={"event": "token", "data": t},
                )
                await asyncio.sleep(0.05)

        # Strip think blocks from final response for history and done event
        clean_response = visible_response.strip() if visible_response else raw_response.strip()
        history.add_message(session_token, "assistant", clean_response)

        # Send done event
        await client.post(
            f"{frontend_url}/internal/stream/{session_token}/chunk",
            json={"event": "done", "data": clean_response},
        )
        logger.info(f"Processed message for session {session_token}")

    except Exception as e:
        logger.error(f"Processing failed for {session_token}: {e}")
        try:
            await client.post(
                f"{frontend_url}/internal/stream/{session_token}/chunk",
                json={"event": "error", "data": f"Processing error: {str(e)}"},
            )
        except Exception:
            pass
    finally:
        await client.aclose()


def _mock_response(content: str) -> str:
    return (
        f'Thank you for your message. You said: "{content}"\n\n'
        "This is a mock response. No LLM provider is currently available. "
        "Please configure LM Studio or Ollama in the admin panel."
    )


async def polling_loop(interval: int = 2):
    """Main polling loop — runs as background task."""
    logger.info(f"Polling loop started (interval: {interval}s)")
    while True:
        try:
            await poll_frontends()
            await process_queue()
        except Exception as e:
            logger.error(f"Polling loop error: {e}")
        await asyncio.sleep(interval)
