import asyncio
import json
import logging
import os
import time
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sidecar")

app = FastAPI(title="HRDD Frontend Sidecar", version="2.0.0")

# Load deployment config
_config_path = os.environ.get("DEPLOYMENT_JSON_PATH", "/app/config/deployment_frontend_worker.json")
_config: dict[str, Any] = {}
if os.path.exists(_config_path):
    with open(_config_path) as f:
        _config = json.load(f)

# --- Message Queue (in-memory, TTL 300s) ---
MESSAGE_TTL = 300
_queue: list[dict[str, Any]] = []
_queue_lock = asyncio.Lock()

# --- SSE Stream Channels ---
# token -> asyncio.Queue of SSE events
_streams: dict[str, asyncio.Queue[dict[str, str]]] = {}
_streams_lock = asyncio.Lock()


class SubmitMessageRequest(BaseModel):
    session_token: str
    content: str
    message_id: str
    timestamp: str
    language: str = "en"
    survey: dict[str, Any] | None = None
    finalize: bool = False


class ChunkRequest(BaseModel):
    event: str  # "token", "done", "error", "queue_position"
    data: str


# --- Health & Config ---

@app.get("/internal/health")
async def health():
    return {"status": "ok"}


@app.get("/internal/config")
async def get_config():
    return {
        "role": "frontend",
        "frontend_type": _config.get("frontend_type", "worker"),
        "session_resume_window_hours": _config.get("session_resume_window_hours", 48),
        "disclaimer_enabled": _config.get("disclaimer_enabled", True),
        "auth_required": _config.get("auth_required", False),
    }


# --- Message Queue ---

@app.post("/internal/queue")
async def enqueue_message(msg: SubmitMessageRequest):
    """React app submits a user message to the queue."""
    async with _queue_lock:
        _queue.append({
            **msg.model_dump(),
            "created_at": time.time(),
        })
    logger.info(f"Enqueued message {msg.message_id} for session {msg.session_token}")
    return {"status": "queued", "message_id": msg.message_id}


@app.get("/internal/queue")
async def dequeue_messages():
    """Backend polls this endpoint to collect pending messages."""
    now = time.time()
    async with _queue_lock:
        # Remove expired messages
        valid = [m for m in _queue if now - m["created_at"] < MESSAGE_TTL]
        _queue.clear()
    logger.info(f"Dequeued {len(valid)} messages")
    return {"messages": valid}


# --- SSE Streaming ---

async def _get_or_create_stream(token: str) -> asyncio.Queue[dict[str, str]]:
    async with _streams_lock:
        if token not in _streams:
            _streams[token] = asyncio.Queue()
        return _streams[token]


@app.post("/internal/stream/{session_token}/chunk")
async def push_chunk(session_token: str, chunk: ChunkRequest):
    """Backend pushes response chunks (tokens) to the stream."""
    q = await _get_or_create_stream(session_token)
    await q.put({"event": chunk.event, "data": chunk.data})

    # Clean up stream on terminal events
    if chunk.event in ("done", "error"):
        # Give SSE consumer time to read, then clean up
        async def _cleanup():
            await asyncio.sleep(5)
            async with _streams_lock:
                _streams.pop(session_token, None)
        asyncio.create_task(_cleanup())

    return {"status": "ok"}


@app.get("/internal/stream/{session_token}")
async def stream_sse(session_token: str):
    """React app opens EventSource here to receive response tokens via SSE."""
    q = await _get_or_create_stream(session_token)

    async def event_generator():
        while True:
            try:
                event = await asyncio.wait_for(q.get(), timeout=30.0)
                yield f"event: {event['event']}\ndata: {event['data']}\n\n"
                if event["event"] in ("done", "error"):
                    break
            except asyncio.TimeoutError:
                # Send keepalive comment to prevent connection timeout
                yield ": keepalive\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
