import asyncio
import json
import logging
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse, FileResponse
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

# --- Recovery Requests (in-memory) ---
# token -> {"status": "pending"|"found"|"not_found"|"expired", "data": {...}}
_recovery: dict[str, dict[str, Any]] = {}
_recovery_lock = asyncio.Lock()

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


class RecoveryDataRequest(BaseModel):
    token: str
    status: str  # "found", "not_found", "expired"
    data: dict[str, Any] | None = None


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

    # Collect pending recovery requests
    recovery_requests = []
    async with _recovery_lock:
        for token, state in _recovery.items():
            if state["status"] == "pending":
                recovery_requests.append(token)

    # Collect pending auth requests
    auth_requests = []
    async with _auth_lock:
        auth_requests = list(_auth_queue)
        _auth_queue.clear()

    result: dict[str, Any] = {"messages": valid}
    if recovery_requests:
        result["recovery_requests"] = recovery_requests
        logger.info(f"Recovery requests: {recovery_requests}")
    if auth_requests:
        result["auth_requests"] = auth_requests
        logger.info(f"Auth requests: {len(auth_requests)}")

    logger.info(f"Dequeued {len(valid)} messages")
    return result


# --- Session Recovery ---

@app.post("/internal/session/recover")
async def request_recovery(data: dict[str, Any]):
    """React app requests session recovery by token."""
    token = data.get("token", "").strip().upper()
    if not token or "-" not in token:
        raise HTTPException(status_code=400, detail="Invalid token format")

    async with _recovery_lock:
        _recovery[token] = {"status": "pending", "data": None, "created_at": time.time()}

    logger.info(f"Recovery requested for {token}")
    return {"status": "pending", "token": token}


@app.get("/internal/session/{token}/recover")
async def get_recovery_status(token: str):
    """React app polls this to check if recovery data is ready."""
    async with _recovery_lock:
        state = _recovery.get(token)

    if not state:
        raise HTTPException(status_code=404, detail="No recovery request for this token")

    if state["status"] == "pending":
        return {"status": "pending"}

    # Recovery resolved — clean up and return
    async with _recovery_lock:
        _recovery.pop(token, None)

    return {"status": state["status"], "data": state.get("data")}


@app.post("/internal/session/{token}/recovery-data")
async def push_recovery_data(token: str, req: RecoveryDataRequest):
    """Backend pushes recovery result (found/not_found/expired + session data)."""
    async with _recovery_lock:
        if token in _recovery:
            _recovery[token] = {
                "status": req.status,
                "data": req.data,
                "created_at": _recovery[token].get("created_at", time.time()),
            }
            logger.info(f"Recovery data pushed for {token}: {req.status}")
        else:
            logger.warning(f"Recovery data for {token} but no pending request")

    # Auto-clean after 60s
    async def _cleanup():
        await asyncio.sleep(60)
        async with _recovery_lock:
            _recovery.pop(token, None)
    asyncio.create_task(_cleanup())

    return {"status": "ok"}


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
                # SSE multi-line: each line needs its own "data:" prefix
                lines = event['data'].split('\n')
                data_block = '\n'.join(f"data: {line}" for line in lines)
                yield f"event: {event['event']}\n{data_block}\n\n"
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


# --- Auth Requests (pull-inverse: sidecar queues, backend resolves) ---
# session_token -> {"status": "pending"|"code_sent"|..., "email": str, ...}
_auth_requests: dict[str, dict[str, Any]] = {}
_auth_queue: list[dict[str, Any]] = []
_auth_lock = asyncio.Lock()


class AuthCodeRequest(BaseModel):
    session_token: str
    email: str
    language: str = "en"


class AuthVerifyRequest(BaseModel):
    session_token: str
    code: str
    language: str = "en"


class AuthResultRequest(BaseModel):
    session_token: str
    status: str  # "code_sent", "verified", "invalid_code", "not_authorized", "smtp_error", "smtp_not_configured"
    email: str = ""


@app.post("/internal/auth/request-code")
async def request_auth_code(req: AuthCodeRequest):
    """React app requests an auth code — queued for backend to process."""
    async with _auth_lock:
        _auth_requests[req.session_token] = {
            "status": "pending",
            "email": req.email,
            "created_at": time.time(),
        }
        _auth_queue.append({
            "session_token": req.session_token,
            "email": req.email,
            "language": req.language,
        })
    logger.info(f"Auth code requested for {req.email} (session {req.session_token})")
    return {"status": "pending"}


@app.post("/internal/auth/verify-code")
async def verify_auth_code(req: AuthVerifyRequest):
    """React app submits a code for verification — queued for backend."""
    async with _auth_lock:
        _auth_requests[req.session_token] = {
            "status": "verifying",
            "email": _auth_requests.get(req.session_token, {}).get("email", ""),
            "created_at": time.time(),
        }
        _auth_queue.append({
            "session_token": req.session_token,
            "code": req.code,
            "email": _auth_requests.get(req.session_token, {}).get("email", ""),
            "language": req.language,
        })
    logger.info(f"Auth code verification for session {req.session_token}")
    return {"status": "verifying"}


@app.get("/internal/auth/status/{session_token}")
async def get_auth_status(session_token: str):
    """React app polls this to check auth result."""
    async with _auth_lock:
        state = _auth_requests.get(session_token)
    if not state:
        return {"status": "none"}
    return {"status": state["status"], "email": state.get("email", "")}


@app.post("/internal/auth/{session_token}/result")
async def push_auth_result(session_token: str, req: AuthResultRequest):
    """Backend pushes auth result (code_sent, verified, rejected, etc.)."""
    async with _auth_lock:
        if session_token in _auth_requests:
            _auth_requests[session_token]["status"] = req.status
            if req.email:
                _auth_requests[session_token]["email"] = req.email
            logger.info(f"Auth result for {session_token}: {req.status}")
        else:
            logger.warning(f"Auth result for {session_token} but no pending request")

    # Auto-clean after 5 minutes
    async def _cleanup():
        await asyncio.sleep(300)
        async with _auth_lock:
            _auth_requests.pop(session_token, None)
    asyncio.create_task(_cleanup())

    return {"status": "ok"}


# --- File Upload ---
# Temp storage for uploads until backend fetches them
UPLOAD_MAX_SIZE = 25 * 1024 * 1024  # 25MB
ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md", ".doc", ".docx", ".jpg", ".jpeg", ".png"}
_upload_dir = Path(tempfile.mkdtemp(prefix="hrdd_uploads_"))
_upload_queue: list[dict[str, str]] = []
_upload_queue_lock = asyncio.Lock()


@app.post("/internal/upload/{session_token}")
async def upload_file(session_token: str, file: UploadFile = File(...)):
    """React app uploads a file for the session."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type {ext} not allowed. Accepted: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    # Read and check size
    content = await file.read()
    if len(content) > UPLOAD_MAX_SIZE:
        raise HTTPException(status_code=400, detail=f"File too large. Maximum: {UPLOAD_MAX_SIZE // (1024*1024)}MB")

    # Save to temp directory
    session_dir = _upload_dir / session_token
    session_dir.mkdir(parents=True, exist_ok=True)
    file_path = session_dir / file.filename
    file_path.write_bytes(content)

    # Queue upload notification for backend
    async with _upload_queue_lock:
        _upload_queue.append({
            "session_token": session_token,
            "filename": file.filename,
            "size": len(content),
            "created_at": time.time(),
        })

    logger.info(f"Upload received: {file.filename} ({len(content)} bytes) for {session_token}")
    return {"status": "uploaded", "filename": file.filename, "size": len(content)}


@app.get("/internal/upload/{session_token}/{filename}")
async def get_upload(session_token: str, filename: str):
    """Backend fetches the uploaded file."""
    file_path = _upload_dir / session_token / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path)


@app.delete("/internal/upload/{session_token}/{filename}")
async def delete_upload(session_token: str, filename: str):
    """Backend confirms receipt — sidecar deletes temp file."""
    file_path = _upload_dir / session_token / filename
    if file_path.exists():
        file_path.unlink()
        logger.info(f"Upload cleaned: {filename} for {session_token}")

    # Clean empty session dir
    session_dir = _upload_dir / session_token
    if session_dir.exists() and not list(session_dir.iterdir()):
        session_dir.rmdir()

    return {"status": "deleted"}


@app.get("/internal/uploads")
async def list_pending_uploads():
    """Backend polls for pending uploads (alongside message queue)."""
    async with _upload_queue_lock:
        uploads = list(_upload_queue)
        _upload_queue.clear()
    return {"uploads": uploads}
