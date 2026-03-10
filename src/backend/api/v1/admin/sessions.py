"""Admin sessions endpoints — list, detail, flag."""

import logging

from fastapi import APIRouter, Depends, HTTPException

from src.api.v1.admin.auth import require_admin
from src.services.session_history import history

logger = logging.getLogger("backend.admin.sessions")

router = APIRouter(prefix="/admin/sessions", tags=["admin-sessions"])


@router.get("")
async def list_sessions(_: dict = Depends(require_admin)):
    """List all active sessions."""
    sessions = history.list_sessions()
    return {"sessions": sessions}


@router.get("/{token}")
async def get_session(token: str, _: dict = Depends(require_admin)):
    """Get session detail with conversation history."""
    session = history.get_session(token)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session not found: {token}")
    return {
        "token": token,
        "survey": session.get("survey", {}),
        "messages": session.get("messages", []),
        "system_prompt": session.get("system_prompt", ""),
        "config": session.get("config", {}),
        "flagged": session.get("flagged", False),
    }


@router.put("/{token}/flag")
async def toggle_flag(token: str, _: dict = Depends(require_admin)):
    """Toggle flag on a session."""
    session = history.get_session(token)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session not found: {token}")
    current = session.get("flagged", False)
    session["flagged"] = not current
    return {"token": token, "flagged": session["flagged"]}
