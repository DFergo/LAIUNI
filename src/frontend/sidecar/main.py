# Copyright (c) 2026 UNI Global Union. All rights reserved. See LICENSE.

import asyncio
import json
import logging
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel

from sidecar.backend_auth import BackendSignatureMiddleware, surface_mode

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sidecar")

# Two surfaces, two apps, two ports (served together by serve.py so they share
# the in-memory state below):
#   app          — public surface, browser routes under /internal/
#   backend_app  — backend surface, routes under /backend/v1/, every request
#                  signed (backend_auth.py). Never reachable on the public port.
app = FastAPI(title="HRDD Frontend Sidecar", version="2.0.0")
backend_app = FastAPI(title="HRDD Frontend Sidecar — backend surface", version="2.0.0",
                      docs_url=None, redoc_url=None, openapi_url=None)
backend_app.add_middleware(BackendSignatureMiddleware)

# Load deployment config (generic — behaviour now comes from the pushed
# frontend config, not this file; kept only for the `role` marker).
_config_path = os.environ.get("DEPLOYMENT_JSON_PATH", "/app/config/deployment_frontend.json")
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
# Open SSE connections per session: a finished stream is only dropped when
# nobody is listening (see _drop_stream_if_idle).
_stream_listeners: dict[str, int] = {}


class SubmitMessageRequest(BaseModel):
    session_token: str
    content: str
    message_id: str
    timestamp: str
    language: str = "en"
    survey: dict[str, Any] | None = None
    finalize: bool = False
    # Sprint 16: filenames the user is "shipping" with this turn (chips).
    # Backend uses this to log + synthesise file-only user messages.
    attachments: list[str] | None = None


class ChunkRequest(BaseModel):
    event: str  # "token", "done", "error", "queue_position"
    data: str


class RecoveryDataRequest(BaseModel):
    token: str
    status: str  # "found", "not_found", "expired"
    data: dict[str, Any] | None = None


# --- Health & Config ---

@app.get("/internal/health")
@backend_app.get("/backend/v1/health")
async def health():
    return {"status": "ok"}


# --- Branding (pushed by backend, translations persisted to disk) ---
_branding: dict[str, Any] = {}
_branding_translations: dict[str, dict[str, str]] = {}
_BRANDING_DIR = Path("/app/data/branding")

# Load translations from disk on startup
if (_BRANDING_DIR / "translations.json").exists():
    try:
        _branding_translations = json.loads((_BRANDING_DIR / "translations.json").read_text())
        logger.info(f"Loaded branding translations: {len(_branding_translations)} languages")
    except (json.JSONDecodeError, OSError):
        pass
if (_BRANDING_DIR / "config.json").exists():
    try:
        _branding = json.loads((_BRANDING_DIR / "config.json").read_text())
        logger.info("Loaded branding config from disk")
    except (json.JSONDecodeError, OSError):
        pass


# Sprint 43: branding tokens (organization / tool name, colours) pushed by the backend with every
# branding update, stored apart from the custom texts so they survive "no custom text" resets.
_tokens: dict[str, str] = {}
_TOKENS_FILE = _BRANDING_DIR / "tokens.json"
_LOGO_SLOTS = ("header", "page", "chat_bg")
if _TOKENS_FILE.exists():
    try:
        _tokens = json.loads(_TOKENS_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        pass


def _logo_file(slot: str, variant: str) -> Path:
    """Stored logo of a slot. Before Sprint 43 there was one logo (logo_color.png /
    logo_white.png) used on the top bar and the pages: still honoured until re-pushed."""
    p = _BRANDING_DIR / f"logo_{slot}_{variant}.png"
    if not p.exists() and slot in ("header", "page"):
        legacy = _BRANDING_DIR / f"logo_{variant}.png"
        if legacy.exists() and (_BRANDING_DIR / "logo_color.png").exists():
            return legacy
    return p


# --- Frontend config (pushed by backend, persisted to disk) — Sprint 21 ---
# A generic frontend starts unconfigured; the backend pushes its config
# (profiles, auth, languages, ...) the same way it pushes branding.
_frontend_config: dict[str, Any] = {}
_FRONTEND_CONFIG_FILE = Path("/app/data/frontend_config.json")
if _FRONTEND_CONFIG_FILE.exists():
    try:
        _frontend_config = json.loads(_FRONTEND_CONFIG_FILE.read_text())
        logger.info("Loaded frontend config from disk")
    except (json.JSONDecodeError, OSError):
        pass


@backend_app.post("/backend/v1/frontend-config")
async def update_frontend_config(data: dict[str, Any]):
    """Backend pushes this frontend's config object."""
    global _frontend_config
    _frontend_config = data
    _FRONTEND_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = _FRONTEND_CONFIG_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    tmp.rename(_FRONTEND_CONFIG_FILE)
    logger.info(f"Frontend config updated: configured={data.get('configured')}")
    return {"status": "ok"}


@backend_app.post("/backend/v1/branding")
async def update_branding(data: dict[str, Any]):
    """Backend pushes branding config + translations for this frontend."""
    global _branding, _branding_translations

    global _tokens
    translations = data.pop("translations", None)
    data.pop("logos", None)  # derived from the files on disk
    is_custom = data.get("custom", False)

    # Tokens are kept whether or not there is custom text
    _BRANDING_DIR.mkdir(parents=True, exist_ok=True)
    if isinstance(data.get("tokens"), dict):
        _tokens = {k: str(v) for k, v in data.pop("tokens").items()}
        tk_tmp = _TOKENS_FILE.with_suffix(".tmp")
        tk_tmp.write_text(json.dumps(_tokens, ensure_ascii=False, indent=2))
        tk_tmp.rename(_TOKENS_FILE)

    # Store base branding
    _branding = data

    if is_custom:
        # Save base config to disk
        cfg_tmp = (_BRANDING_DIR / "config.json").with_suffix(".tmp")
        cfg_tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        cfg_tmp.rename(_BRANDING_DIR / "config.json")

        # Save translations if provided
        if translations:
            _branding_translations = translations
            tr_tmp = (_BRANDING_DIR / "translations.json").with_suffix(".tmp")
            tr_tmp.write_text(json.dumps(translations, ensure_ascii=False, indent=2))
            tr_tmp.rename(_BRANDING_DIR / "translations.json")
            logger.info(f"Branding translations saved: {len(translations)} languages")
    else:
        # Reset to default — delete branding files
        _branding_translations = {}
        for f in ("translations.json", "config.json"):
            p = _BRANDING_DIR / f
            if p.exists():
                p.unlink()
        logger.info("Branding reset to default, files deleted")

    logger.info(f"Branding updated: custom={is_custom}")
    return {"status": "ok"}


@app.get("/internal/branding/{lang_code}")
async def get_branding_translation(lang_code: str):
    """Get translated branding text for a specific language."""
    if lang_code in _branding_translations:
        return _branding_translations[lang_code]
    # Fallback: return base branding text (untranslated)
    return {
        "disclaimer_text": _branding.get("disclaimer_text", ""),
        "instructions_text": _branding.get("instructions_text", ""),
    }


@backend_app.post("/backend/v1/branding-logo")
async def update_branding_logo(
    mode: str = Form("white"),
    clear: str = Form(""),
    slot: str = Form(""),
    color: UploadFile | None = File(None),
    white: UploadFile | None = File(None),
):
    """Backend pushes the processed logo variants of one slot + the header mode (Sprint 33, slots Sprint 43).
    Without `slot` (a backend from before Sprint 43) the logo serves the top bar and the pages."""
    if slot and slot not in _LOGO_SLOTS:
        raise HTTPException(status_code=400, detail="Unknown slot")
    _BRANDING_DIR.mkdir(parents=True, exist_ok=True)
    slots = [slot] if slot else ["header", "page"]

    if clear:
        for sl in slots:
            for variant in ("color", "white"):
                (_BRANDING_DIR / f"logo_{sl}_{variant}.png").unlink(missing_ok=True)
        if not slot:  # legacy files too
            for variant in ("color", "white"):
                (_BRANDING_DIR / f"logo_{variant}.png").unlink(missing_ok=True)
        (_BRANDING_DIR / "logo_meta.json").write_text(json.dumps({"mode": mode}))
        logger.info(f"Branding logo cleared ({', '.join(slots)})")
        return {"status": "ok"}

    if color is not None:
        color_bytes = await color.read()
        white_bytes = await white.read() if white is not None else None
        for sl in slots:
            (_BRANDING_DIR / f"logo_{sl}_color.png").write_bytes(color_bytes)
            if white_bytes is not None:
                (_BRANDING_DIR / f"logo_{sl}_white.png").write_bytes(white_bytes)
            else:  # white accompanies a fresh upload; drop any stale one
                (_BRANDING_DIR / f"logo_{sl}_white.png").unlink(missing_ok=True)
        if not slot:
            for variant in ("color", "white"):
                (_BRANDING_DIR / f"logo_{variant}.png").unlink(missing_ok=True)
    # meta always reflects the latest mode (mode-only toggles re-push here too)
    (_BRANDING_DIR / "logo_meta.json").write_text(json.dumps({"mode": mode}))
    logger.info(f"Branding logo updated ({', '.join(slots)}, mode={mode})")
    return {"status": "ok"}


@app.get("/internal/branding-logo/{slot}/{variant}")
async def get_branding_logo_slot(slot: str, variant: str):
    """Serve a stored logo variant of a slot; 404 lets the React app fall back to logo_url/default."""
    if slot not in _LOGO_SLOTS or variant not in ("color", "white"):
        raise HTTPException(status_code=404, detail="Unknown logo")
    p = _logo_file(slot, variant)
    if not p.exists():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(p, media_type="image/png")


@app.get("/internal/branding-logo/{variant}")
async def get_branding_logo(variant: str):
    """Top-bar logo (route kept from before Sprint 43)."""
    if variant not in ("color", "white"):
        raise HTTPException(status_code=404, detail="Unknown variant")
    p = _logo_file("header", variant)
    if not p.exists():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(p, media_type="image/png")


@app.get("/internal/config")
@backend_app.get("/backend/v1/config")
async def get_config():
    if _frontend_config.get("configured"):
        cfg = {
            "role": "frontend",
            "configured": True,
            "profiles": _frontend_config.get("profiles", []),
            "auth": _frontend_config.get("auth", {}),
            "auth_required": _frontend_config.get("auth_required", False),
            "languages": _frontend_config.get("languages", []),
            "modes": _frontend_config.get("modes", {}),
            "display_names": _frontend_config.get("display_names", {"profiles": {}, "modes": {}}),
            "session_resume_window_hours": _frontend_config.get("session_resume_window_hours", 48),
            "disclaimer_enabled": _frontend_config.get("disclaimer_enabled", True),
            "data_protection_email": _frontend_config.get("data_protection_email", ""),
        }
    else:
        cfg = {"role": "frontend", "configured": False}
    # Logo state is derived from disk (source of truth), so it survives restarts
    # and works even when there is no custom text branding.
    logos = {sl: {"uploaded": _logo_file(sl, "color").exists(), "has_white": _logo_file(sl, "white").exists()}
             for sl in _LOGO_SLOTS}
    logo_mode = "white"
    meta = _BRANDING_DIR / "logo_meta.json"
    if meta.exists():
        try:
            logo_mode = json.loads(meta.read_text()).get("mode", "white")
        except (json.JSONDecodeError, OSError):
            pass

    if _branding or _tokens or any(l["uploaded"] for l in logos.values()):
        cfg["branding"] = {
            "app_title": _branding.get("app_title", ""),
            "logo_url": _branding.get("logo_url", ""),
            "custom": _branding.get("custom", False),
            "logo_mode": logo_mode,
            "logo_uploaded": logos["header"]["uploaded"],
            "logo_has_white": logos["header"]["has_white"],
            "logos": logos,
            "tokens": _tokens,
        }
    return cfg


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


@backend_app.get("/backend/v1/queue")
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

    # Collect pending evidence-delete requests (Sprint 16)
    async with _evidence_delete_lock:
        evidence_delete_requests = list(_evidence_delete_queue)
        _evidence_delete_queue.clear()

    # surface_auth lets the backend show the frontend's real auth mode in the admin
    result: dict[str, Any] = {"messages": valid, "surface_auth": surface_mode()}
    if recovery_requests:
        result["recovery_requests"] = recovery_requests
        logger.info(f"Recovery requests: {recovery_requests}")
    if auth_requests:
        result["auth_requests"] = auth_requests
        logger.info(f"Auth requests: {len(auth_requests)}")
    if evidence_delete_requests:
        result["evidence_delete_requests"] = evidence_delete_requests
        logger.info(f"Evidence delete requests: {len(evidence_delete_requests)}")

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


@backend_app.post("/backend/v1/session/{token}/recovery-data")
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


@backend_app.post("/backend/v1/stream/{session_token}/chunk")
async def push_chunk(session_token: str, chunk: ChunkRequest):
    """Backend pushes response chunks (tokens) to the stream."""
    q = await _get_or_create_stream(session_token)
    await q.put({"event": chunk.event, "data": chunk.data})

    # Clean up stream on terminal events
    if chunk.event in ("done", "error"):
        # Give SSE consumer time to read, then clean up — unless a browser is
        # already listening for the next message on this session (it opens its
        # stream before sending; dropping the queue under it would lose the reply).
        async def _cleanup():
            await asyncio.sleep(5)
            await _drop_stream_if_idle(session_token, q)
        asyncio.create_task(_cleanup())

    return {"status": "ok"}


async def _drop_stream_if_idle(token: str, q: asyncio.Queue) -> bool:
    """Drop a finished session stream if it is still the current one and no SSE
    connection is listening to it. Returns True if it was dropped."""
    async with _streams_lock:
        if _streams.get(token) is q and not _stream_listeners.get(token):
            _streams.pop(token, None)
            return True
        return False


@app.get("/internal/stream/{session_token}")
async def stream_sse(session_token: str):
    """React app opens EventSource here to receive response tokens via SSE."""
    q = await _get_or_create_stream(session_token)

    async def event_generator():
        _stream_listeners[session_token] = _stream_listeners.get(session_token, 0) + 1
        try:
            async for chunk in _sse_events(q):
                yield chunk
        finally:
            left = _stream_listeners.get(session_token, 1) - 1
            if left > 0:
                _stream_listeners[session_token] = left
            else:
                _stream_listeners.pop(session_token, None)

    async def _sse_events(q):
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


@backend_app.post("/backend/v1/auth/{session_token}/result")
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


@backend_app.get("/backend/v1/upload/{session_token}/{filename}")
async def get_upload(session_token: str, filename: str):
    """Backend fetches the uploaded file."""
    file_path = _upload_dir / session_token / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path)


@backend_app.delete("/backend/v1/upload/{session_token}/{filename}")
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


@backend_app.get("/backend/v1/uploads")
async def list_pending_uploads():
    """Backend polls for pending uploads (alongside message queue)."""
    async with _upload_queue_lock:
        uploads = list(_upload_queue)
        _upload_queue.clear()
    return {"uploads": uploads}


# --- Evidence Deletion (Sprint 16 — Claude-Style retraction) ---
# Queue of pending evidence-delete requests {token, filename}.
# Drained by the backend on its next /internal/queue poll.
_evidence_delete_queue: list[dict[str, str]] = []
_evidence_delete_lock = asyncio.Lock()


@app.delete("/internal/evidence/{session_token}/{filename}")
async def request_evidence_delete(session_token: str, filename: str):
    """React app retracts a previously uploaded file.

    Enqueues the deletion for the backend to handle on its next poll.
    Returns 202 immediately. The frontend optimistically removes the chip
    and waits for an `evidence_deleted` SSE event for confirmation (or
    `evidence_delete_error` for failure).
    """
    if not filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    async with _evidence_delete_lock:
        _evidence_delete_queue.append({
            "token": session_token,
            "filename": filename,
        })
    logger.info(f"Evidence delete queued: {filename} for {session_token}")
    return {"status": "queued"}
