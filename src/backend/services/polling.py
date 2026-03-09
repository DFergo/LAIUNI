import asyncio
import logging
import time
from collections import deque
from typing import Any

import httpx

from src.services.frontend_registry import registry

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

    client = httpx.AsyncClient(timeout=30.0)
    try:
        # Mock LLM response — Sprint 5 will replace this with real LLM
        mock_response = f"Thank you for your message. You said: \"{content}\"\n\nThis is a mock response. Real AI responses will be available after LLM integration (Sprint 5)."

        # Stream mock response token by token
        words = mock_response.split(" ")
        for i, word in enumerate(words):
            token = word if i == 0 else " " + word
            await client.post(
                f"{frontend_url}/internal/stream/{session_token}/chunk",
                json={"event": "token", "data": token},
            )
            await asyncio.sleep(0.05)  # Simulate streaming delay

        # Send done event with full text
        await client.post(
            f"{frontend_url}/internal/stream/{session_token}/chunk",
            json={"event": "done", "data": mock_response},
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
