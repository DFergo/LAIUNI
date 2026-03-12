"""Disk-backed session store with in-memory cache for active sessions.

Sprint 8a: Replaces session_history.py (in-memory only).
All session data persisted to /app/data/sessions/{token}/:
  - session.json   — metadata (survey, language, role, mode, timestamps, status, flagged)
  - conversation.jsonl — one JSON line per message {role, content, timestamp}

In-memory cache keeps active sessions fast. Disk is source of truth.
"""

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.core.config import config

logger = logging.getLogger("backend.session_store")


def _sessions_dir() -> Path:
    return Path(config.sessions_path)


def _session_dir(token: str) -> Path:
    return _sessions_dir() / token


def _atomic_write_json(path: Path, data: dict):
    """Write JSON atomically (tmp + rename)."""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str))
    tmp.rename(path)


class SessionStore:
    """Disk-backed session store with in-memory cache."""

    def __init__(self):
        self._cache: dict[str, dict[str, Any]] = {}
        self._loaded = False

    def _ensure_loaded(self):
        """Scan disk for existing sessions on first access."""
        if self._loaded:
            return
        self._loaded = True
        sessions_dir = _sessions_dir()
        if not sessions_dir.exists():
            sessions_dir.mkdir(parents=True, exist_ok=True)
            return

        count = 0
        for d in sessions_dir.iterdir():
            if d.is_dir() and (d / "session.json").exists():
                try:
                    meta = json.loads((d / "session.json").read_text())
                    if meta.get("archived"):
                        continue  # Skip archived sessions
                    messages = self._load_conversation(d.name)
                    self._cache[d.name] = {
                        "system_prompt": meta.get("system_prompt", ""),
                        "messages": messages,
                        "survey": meta.get("survey", {}),
                        "config": meta.get("config", {}),
                        "language": meta.get("language", "en"),
                        "frontend_name": meta.get("frontend_name", ""),
                        "frontend_id": meta.get("frontend_id", ""),
                        "status": meta.get("status", "active"),
                        "flagged": meta.get("flagged", False),
                        "created_at": meta.get("created_at"),
                        "last_activity": meta.get("last_activity"),
                        "guardrail_violations": meta.get("guardrail_violations", 0),
                    }
                    count += 1
                except Exception as e:
                    logger.warning(f"Failed to load session {d.name}: {e}")

        if count:
            logger.info(f"Loaded {count} sessions from disk")

    def _load_conversation(self, token: str) -> list[dict[str, str]]:
        """Read conversation.jsonl from disk."""
        path = _session_dir(token) / "conversation.jsonl"
        if not path.exists():
            return []
        messages = []
        for line in path.read_text().splitlines():
            line = line.strip()
            if line:
                try:
                    messages.append(json.loads(line))
                except json.JSONDecodeError:
                    logger.warning(f"Bad JSONL line in {token}")
        return messages

    def _save_meta(self, token: str):
        """Write session.json to disk."""
        session = self._cache.get(token)
        if not session:
            return
        d = _session_dir(token)
        d.mkdir(parents=True, exist_ok=True)

        meta = {
            "survey": session.get("survey", {}),
            "language": session.get("language", "en"),
            "role": session.get("survey", {}).get("role", "unknown"),
            "mode": session.get("survey", {}).get("type", "documentation"),
            "status": session.get("status", "active"),
            "flagged": session.get("flagged", False),
            "system_prompt": session.get("system_prompt", ""),
            "config": session.get("config", {}),
            "created_at": session.get("created_at"),
            "last_activity": session.get("last_activity"),
            "frontend_name": session.get("frontend_name", ""),
            "frontend_id": session.get("frontend_id", ""),
            "guardrail_violations": session.get("guardrail_violations", 0),
        }
        _atomic_write_json(d / "session.json", meta)

    def _append_message(self, token: str, role: str, content: str, timestamp: str):
        """Append one message to conversation.jsonl."""
        d = _session_dir(token)
        d.mkdir(parents=True, exist_ok=True)
        path = d / "conversation.jsonl"
        line = json.dumps({"role": role, "content": content, "timestamp": timestamp})
        with open(path, "a") as f:
            f.write(line + "\n")

    # --- Public API (compatible with session_history.py interface) ---

    def init_session(
        self,
        token: str,
        system_prompt: str,
        survey: dict[str, Any] | None = None,
        language: str = "en",
        frontend_name: str = "",
        frontend_id: str = "",
    ):
        """Initialize or reinitialize a session."""
        self._ensure_loaded()
        now = datetime.now(timezone.utc).isoformat()

        if token not in self._cache:
            self._cache[token] = {
                "system_prompt": system_prompt,
                "messages": [],
                "survey": survey or {},
                "config": {},
                "language": language,
                "frontend_name": frontend_name,
                "frontend_id": frontend_id,
                "status": "active",
                "flagged": False,
                "created_at": now,
                "last_activity": now,
            }
            logger.info(f"Session initialized: {token}")
        else:
            self._cache[token]["system_prompt"] = system_prompt
            if survey:
                self._cache[token]["survey"] = survey
            if language:
                self._cache[token]["language"] = language

        self._save_meta(token)

    def add_message(self, token: str, role: str, content: str):
        """Add a message to session history (memory + disk)."""
        self._ensure_loaded()
        self._ensure_session(token)
        now = datetime.now(timezone.utc).isoformat()

        self._cache[token]["messages"].append({
            "role": role,
            "content": content,
            "timestamp": now,
        })
        self._cache[token]["last_activity"] = now

        # Persist to disk
        self._append_message(token, role, content, now)
        self._save_meta(token)  # Update last_activity

    def _ensure_session(self, token: str):
        """Create a minimal session if it doesn't exist in cache."""
        if token not in self._cache:
            now = datetime.now(timezone.utc).isoformat()
            self._cache[token] = {
                "system_prompt": "",
                "messages": [],
                "survey": {},
                "config": {},
                "language": "en",
                "status": "active",
                "flagged": False,
                "created_at": now,
                "last_activity": now,
            }

    def get_llm_messages(self, token: str) -> list[dict[str, str]]:
        """Get the full message list for LLM inference (system + history)."""
        self._ensure_loaded()
        self._ensure_session(token)
        session = self._cache[token]
        messages: list[dict[str, str]] = []

        if session["system_prompt"]:
            messages.append({
                "role": "system",
                "content": session["system_prompt"],
            })

        # Strip timestamps for LLM (only role + content needed)
        for msg in session["messages"]:
            messages.append({
                "role": msg["role"],
                "content": msg["content"],
            })

        return messages

    def get_session_config(self, token: str) -> dict[str, Any]:
        """Get session-specific config overrides."""
        self._ensure_loaded()
        self._ensure_session(token)
        return self._cache[token].get("config", {})

    def get_session(self, token: str) -> dict[str, Any] | None:
        """Get full session data."""
        self._ensure_loaded()
        return self._cache.get(token)

    def list_sessions(self) -> list[dict[str, Any]]:
        """List all sessions with metadata."""
        self._ensure_loaded()
        result = []
        for token, data in self._cache.items():
            result.append({
                "token": token,
                "message_count": len(data["messages"]),
                "role": data.get("survey", {}).get("role", "unknown"),
                "mode": data.get("survey", {}).get("type", "documentation"),
                "company": data.get("survey", {}).get("company", ""),
                "frontend_name": data.get("frontend_name", ""),
                "frontend_id": data.get("frontend_id", ""),
                "status": data.get("status", "active"),
                "flagged": data.get("flagged", False),
                "guardrail_violations": data.get("guardrail_violations", 0),
                "created_at": data.get("created_at"),
                "last_activity": data.get("last_activity"),
            })
        return result

    def toggle_flag(self, token: str) -> bool:
        """Toggle flagged status. Returns new value."""
        self._ensure_loaded()
        session = self._cache.get(token)
        if not session:
            return False
        session["flagged"] = not session.get("flagged", False)
        self._save_meta(token)
        return session["flagged"]

    def increment_guardrail_violations(self, token: str) -> int:
        """Increment guardrail violation count. Returns new count."""
        self._ensure_loaded()
        session = self._cache.get(token)
        if not session:
            return 0
        count = session.get("guardrail_violations", 0) + 1
        session["guardrail_violations"] = count
        self._save_meta(token)
        return count

    def get_guardrail_violations(self, token: str) -> int:
        """Get current guardrail violation count."""
        self._ensure_loaded()
        session = self._cache.get(token)
        if not session:
            return 0
        return session.get("guardrail_violations", 0)

    def set_status(self, token: str, status: str):
        """Set session status (active/completed/flagged)."""
        self._ensure_loaded()
        session = self._cache.get(token)
        if session:
            session["status"] = status
            self._save_meta(token)

    def archive_session(self, token: str):
        """Archive a session: mark in session.json and remove from cache. Files stay on disk."""
        session = self._cache.get(token)
        if session:
            session["archived"] = True
            session["archived_at"] = datetime.now(timezone.utc).isoformat()
            self._save_meta(token)
        else:
            # Not in cache but might be on disk
            d = _session_dir(token)
            meta_path = d / "session.json"
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text())
                    meta["archived"] = True
                    meta["archived_at"] = datetime.now(timezone.utc).isoformat()
                    _atomic_write_json(meta_path, meta)
                except Exception as e:
                    logger.warning(f"Failed to archive {token} on disk: {e}")
        self._cache.pop(token, None)
        logger.info(f"Session archived: {token}")

    def remove_session(self, token: str):
        """Remove a session from cache (disk files kept for audit)."""
        self._cache.pop(token, None)


# Singleton
store = SessionStore()
