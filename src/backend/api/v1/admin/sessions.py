"""Admin sessions endpoints — list, detail, flag, documents, lifecycle."""

import logging
import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.api.v1.admin.auth import require_admin
from src.services.session_store import store
from src.services.session_lifecycle import load_lifecycle_settings, save_lifecycle_settings, DEFAULT_CONFIG

logger = logging.getLogger("backend.admin.sessions")

router = APIRouter(prefix="/admin/sessions", tags=["admin-sessions"])

SESSIONS_DIR = "/app/data/sessions"
DOC_FILES = {
    "summary": "summary.md",
    "internal_summary": "internal_summary.md",
    "report": "report.md",
}


@router.get("")
async def list_sessions(_: dict = Depends(require_admin)):
    """List all sessions (active + completed) with document status."""
    sessions = store.list_sessions()
    for s in sessions:
        token = s["token"]
        s["docs"] = {
            doc_type: os.path.exists(os.path.join(SESSIONS_DIR, token, filename))
            for doc_type, filename in DOC_FILES.items()
        }
    return {"sessions": sessions}


# --- Lifecycle settings (MUST be before /{token} routes) ---

class LifecycleConfig(BaseModel):
    auto_close_enabled: bool = False
    auto_close_hours: int = 2
    auto_cleanup_enabled: bool = False
    auto_cleanup_days: int = 30


@router.get("/lifecycle")
async def get_lifecycle(_: dict = Depends(require_admin)):
    """Get lifecycle settings for all frontends."""
    settings = load_lifecycle_settings()
    return {"settings": settings, "defaults": DEFAULT_CONFIG}


@router.put("/lifecycle/{frontend_id}")
async def update_lifecycle(frontend_id: str, config: LifecycleConfig, _: dict = Depends(require_admin)):
    """Update lifecycle settings for a specific frontend."""
    settings = load_lifecycle_settings()
    settings[frontend_id] = config.model_dump()
    save_lifecycle_settings(settings)
    return {"frontend_id": frontend_id, "config": settings[frontend_id]}


@router.get("/{token}")
async def get_session(token: str, _: dict = Depends(require_admin)):
    """Get session detail with conversation history."""
    session = store.get_session(token)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session not found: {token}")
    return {
        "token": token,
        "survey": session.get("survey", {}),
        "messages": session.get("messages", []),
        "system_prompt": session.get("system_prompt", ""),
        "config": session.get("config", {}),
        "flagged": session.get("flagged", False),
        "status": session.get("status", "active"),
        "language": session.get("language", "en"),
        "created_at": session.get("created_at"),
        "last_activity": session.get("last_activity"),
    }


@router.put("/{token}/flag")
async def toggle_flag(token: str, _: dict = Depends(require_admin)):
    """Toggle flag on a session. Persists to disk."""
    session = store.get_session(token)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session not found: {token}")
    new_flag = store.toggle_flag(token)
    return {"token": token, "flagged": new_flag}


@router.get("/{token}/documents")
async def get_documents(token: str, _: dict = Depends(require_admin)):
    """Read all available documents for a session."""
    session = store.get_session(token)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session not found: {token}")

    docs: dict[str, str | None] = {}
    session_dir = os.path.join(SESSIONS_DIR, token)
    for doc_type, filename in DOC_FILES.items():
        path = os.path.join(session_dir, filename)
        if os.path.exists(path):
            with open(path) as f:
                docs[doc_type] = f.read()
        else:
            docs[doc_type] = None

    return {"token": token, "documents": docs}


@router.post("/{token}/generate/{doc_type}")
async def generate_document(token: str, doc_type: str, _: dict = Depends(require_admin)):
    """Trigger on-demand generation of a document."""
    if doc_type not in DOC_FILES:
        raise HTTPException(status_code=400, detail=f"Invalid doc type: {doc_type}. Valid: {list(DOC_FILES.keys())}")

    session = store.get_session(token)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session not found: {token}")

    if not session.get("messages"):
        raise HTTPException(status_code=400, detail="Session has no messages")

    from src.services.polling import _generate_document
    from src.api.v1.admin.llm import get_llm_settings

    language = session.get("language", "en")
    role = session.get("survey", {}).get("role", "worker")
    settings = get_llm_settings()
    session_dir = os.path.join(SESSIONS_DIR, token)
    os.makedirs(session_dir, exist_ok=True)

    try:
        if doc_type == "summary":
            # Summary uses per-profile prompt
            prompt_file = f"session_summary_{role}.md"
            content = await _generate_document(token, prompt_file, language, settings)
            if not content:
                # Fallback to generic
                content = await _generate_document(token, "session_summary.md", language, settings)
        elif doc_type == "internal_summary":
            content = await _generate_document(token, "session_summary_uni.md", language, settings)
        elif doc_type == "report":
            content = await _generate_document(token, "internal_case_file.md", language, settings)
        else:
            content = None

        if not content:
            raise HTTPException(status_code=500, detail="Generation produced no content")

        # Save to disk
        path = os.path.join(session_dir, DOC_FILES[doc_type])
        with open(path, "w") as f:
            f.write(content)
        logger.info(f"Admin generated {doc_type} for {token}")

        return {"token": token, "doc_type": doc_type, "content": content}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Admin generation failed ({doc_type} for {token}): {e}")
        raise HTTPException(status_code=500, detail=f"Generation failed: {str(e)}")
