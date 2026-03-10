"""In-memory conversation history per session.

Maintains system prompt + message history for LLM context.
Session persistence to disk will come in Sprint 8.
"""

import logging
from typing import Any

logger = logging.getLogger("backend.sessions")


class SessionHistory:
    """Stores conversation history per session token."""

    def __init__(self):
        # token -> {"system_prompt": str, "messages": [...], "survey": {...}, "config": {...}}
        self._sessions: dict[str, dict[str, Any]] = {}

    def init_session(
        self,
        token: str,
        system_prompt: str,
        survey: dict[str, Any] | None = None,
    ):
        """Initialize or reinitialize a session with its system prompt."""
        if token not in self._sessions:
            self._sessions[token] = {
                "system_prompt": system_prompt,
                "messages": [],
                "survey": survey or {},
                "config": {},
            }
            logger.info(f"Session initialized: {token}")
        else:
            # Update system prompt if re-initializing
            self._sessions[token]["system_prompt"] = system_prompt
            if survey:
                self._sessions[token]["survey"] = survey

    def _ensure_session(self, token: str):
        """Create a minimal session if it doesn't exist yet."""
        if token not in self._sessions:
            self._sessions[token] = {
                "system_prompt": "",
                "messages": [],
                "survey": {},
                "config": {},
            }

    def add_message(self, token: str, role: str, content: str):
        """Add a message to the session history."""
        self._ensure_session(token)
        self._sessions[token]["messages"].append({
            "role": role,
            "content": content,
        })

    def get_llm_messages(self, token: str) -> list[dict[str, str]]:
        """Get the full message list for LLM inference (system + history)."""
        self._ensure_session(token)
        session = self._sessions[token]
        messages: list[dict[str, str]] = []

        # System prompt
        if session["system_prompt"]:
            messages.append({
                "role": "system",
                "content": session["system_prompt"],
            })

        # Conversation history
        messages.extend(session["messages"])

        return messages

    def get_session_config(self, token: str) -> dict[str, Any]:
        """Get session-specific config overrides."""
        self._ensure_session(token)
        return self._sessions[token].get("config", {})

    def get_session(self, token: str) -> dict[str, Any] | None:
        """Get full session data."""
        return self._sessions.get(token)

    def list_sessions(self) -> list[dict[str, Any]]:
        """List all active sessions with metadata."""
        result = []
        for token, data in self._sessions.items():
            result.append({
                "token": token,
                "message_count": len(data["messages"]),
                "role": data.get("survey", {}).get("role", "unknown"),
                "mode": data.get("survey", {}).get("type", "documentation"),
            })
        return result

    def remove_session(self, token: str):
        """Remove a session from memory."""
        self._sessions.pop(token, None)


# Singleton
history = SessionHistory()
