"""Background task: auto-close inactive sessions and clean up old ones.

Sprint 8f: Scans every 5 minutes. Per-frontend configurable timeouts.
- Auto-closure: generates documents (summary, internal_summary, report) without streaming
- Auto-cleanup: removes completed sessions from listing (files stay on disk)
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("backend.session_lifecycle")

DATA_DIR = Path("/app/data")
LIFECYCLE_FILE = DATA_DIR / "session_lifecycle.json"

SCAN_INTERVAL = 300  # 5 minutes

# Defaults when no per-frontend config exists
DEFAULT_CONFIG = {
    "auto_close_enabled": False,
    "auto_close_hours": 2,
    "auto_cleanup_enabled": False,
    "auto_cleanup_days": 30,
}


def _atomic_write_json(path: Path, data: Any):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str))
    tmp.rename(path)


def load_lifecycle_settings() -> dict[str, dict[str, Any]]:
    """Load per-frontend lifecycle settings. Returns {frontend_id: config}."""
    if LIFECYCLE_FILE.exists():
        try:
            return json.loads(LIFECYCLE_FILE.read_text())
        except Exception as e:
            logger.error(f"Failed to load lifecycle settings: {e}")
    return {}


def save_lifecycle_settings(settings: dict[str, dict[str, Any]]):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _atomic_write_json(LIFECYCLE_FILE, settings)


def get_frontend_config(frontend_id: str) -> dict[str, Any]:
    """Get lifecycle config for a frontend, with defaults."""
    settings = load_lifecycle_settings()
    config = settings.get(frontend_id, {})
    return {**DEFAULT_CONFIG, **config}


async def lifecycle_loop():
    """Background loop: scan sessions every SCAN_INTERVAL seconds."""
    logger.info("Session lifecycle scanner started")
    while True:
        await asyncio.sleep(SCAN_INTERVAL)
        try:
            logger.info("Lifecycle scan running...")
            await _scan_sessions()
            logger.info("Lifecycle scan complete")
        except Exception as e:
            logger.error(f"Lifecycle scan error: {e}", exc_info=True)


async def _scan_sessions():
    """One scan cycle: check for inactive sessions and old completed sessions."""
    from src.services.session_store import store
    from src.services.frontend_registry import registry

    settings = load_lifecycle_settings()
    now = datetime.now(timezone.utc)
    sessions = store.list_sessions()

    if not sessions:
        return

    # Build frontend_name → frontend_id mapping (fallback for sessions without frontend_id)
    name_to_id: dict[str, str] = {}
    for f in registry.list_all():
        name_to_id[f.get("name", "")] = f["id"]

    for session in sessions:
        token = session["token"]
        status = session.get("status", "active")
        frontend_id = session.get("frontend_id", "")

        # Fallback: resolve frontend_id from frontend_name
        if not frontend_id:
            frontend_name = session.get("frontend_name", "")
            frontend_id = name_to_id.get(frontend_name, "")

        # Get config for this frontend (or defaults)
        config = {**DEFAULT_CONFIG, **(settings.get(frontend_id, {}) if frontend_id else {})}

        last_activity_str = session.get("last_activity")
        if not last_activity_str:
            continue

        try:
            last_activity = datetime.fromisoformat(last_activity_str)
        except (ValueError, TypeError):
            continue

        inactive_hours = (now - last_activity).total_seconds() / 3600

        # Auto-close active sessions
        if status == "active" and config["auto_close_enabled"]:
            if inactive_hours >= config["auto_close_hours"]:
                await _auto_close_session(token, session)

        # Auto-cleanup completed sessions
        elif status == "completed" and config["auto_cleanup_enabled"]:
            inactive_days = inactive_hours / 24
            if inactive_days >= config["auto_cleanup_days"]:
                _auto_cleanup_session(token)


async def _auto_close_session(token: str, session_meta: dict[str, Any]):
    """Auto-close an inactive session: generate documents and mark completed."""
    from src.services.session_store import store
    from src.services.polling import _generate_document, _generate_internal_documents
    from src.api.v1.admin.llm import get_llm_settings

    logger.info(f"Auto-closing inactive session: {token}")

    full_session = store.get_session(token)
    if not full_session:
        return

    if not full_session.get("messages"):
        # No messages — just mark completed, no documents to generate
        store.set_status(token, "completed")
        logger.info(f"Auto-closed empty session: {token}")
        return

    language = full_session.get("language", "en")
    role = full_session.get("survey", {}).get("role", "worker")
    mode = full_session.get("survey", {}).get("type", "documentation")
    settings = get_llm_settings()
    session_dir = f"/app/data/sessions/{token}"

    import os
    os.makedirs(session_dir, exist_ok=True)

    # 1. Generate user summary (not streamed — user is gone)
    try:
        prompt_file = f"session_summary_{role}.md"
        content = await _generate_document(token, prompt_file, language, settings)
        if not content:
            content = await _generate_document(token, "session_summary.md", language, settings)
        if content:
            path = os.path.join(session_dir, "summary.md")
            tmp = path + ".tmp"
            with open(tmp, "w") as f:
                f.write(content)
            os.replace(tmp, path)
            # Save as conversation message too
            store.add_message(token, "assistant", content)
            logger.info(f"Auto-close summary saved: {token}")
    except Exception as e:
        logger.error(f"Auto-close summary failed for {token}: {e}")

    # 2. Mark completed
    store.set_status(token, "completed")

    # 3. Generate internal documents (same as manual closure)
    try:
        await _generate_internal_documents(token, language, mode, settings)
    except Exception as e:
        logger.error(f"Auto-close internal docs failed for {token}: {e}")

    logger.info(f"Auto-close complete: {token}")


def _auto_cleanup_session(token: str):
    """Remove a session from the store listing. Files on disk are preserved."""
    from src.services.session_store import store

    logger.info(f"Auto-cleanup: archiving session {token}")
    store.archive_session(token)
