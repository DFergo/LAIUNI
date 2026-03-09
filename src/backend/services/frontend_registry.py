import json
import logging
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("backend.registry")

DATA_DIR = Path(os.environ.get("HRDD_DATA_DIR", "/app/data"))
REGISTRY_FILE = DATA_DIR / "frontends.json"


class FrontendRegistry:
    """Persistent registry of frontend instances. Atomic JSON writes (lesson #5)."""

    def __init__(self):
        self._frontends: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self):
        if REGISTRY_FILE.exists():
            try:
                self._frontends = json.loads(REGISTRY_FILE.read_text())
                logger.info(f"Loaded {len(self._frontends)} frontends from registry")
            except Exception as e:
                logger.error(f"Failed to load registry: {e}")
                self._frontends = {}

    def _save(self):
        """Atomic write: write to temp file, then rename (lesson #5)."""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        tmp = REGISTRY_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._frontends, indent=2))
        tmp.rename(REGISTRY_FILE)

    def register(self, url: str, frontend_type: str, name: str = "") -> dict[str, Any]:
        # Check if URL already registered
        for fid, f in self._frontends.items():
            if f["url"] == url:
                return f

        fid = secrets.token_hex(4)
        now = datetime.now(timezone.utc).isoformat()
        frontend = {
            "id": fid,
            "url": url.rstrip("/"),
            "frontend_type": frontend_type,
            "name": name or f"{frontend_type}-{fid[:4]}",
            "enabled": True,
            "status": "unknown",
            "last_seen": None,
            "created_at": now,
        }
        self._frontends[fid] = frontend
        self._save()
        logger.info(f"Registered frontend {fid}: {url} ({frontend_type})")
        return frontend

    def remove(self, fid: str) -> bool:
        if fid in self._frontends:
            del self._frontends[fid]
            self._save()
            return True
        return False

    def update(self, fid: str, **kwargs: Any) -> dict[str, Any] | None:
        if fid not in self._frontends:
            return None
        self._frontends[fid].update(kwargs)
        self._save()
        return self._frontends[fid]

    def set_status(self, fid: str, status: str):
        if fid in self._frontends:
            self._frontends[fid]["status"] = status
            if status == "online":
                self._frontends[fid]["last_seen"] = datetime.now(timezone.utc).isoformat()
            # Don't save on every status update — it's runtime state

    def get(self, fid: str) -> dict[str, Any] | None:
        return self._frontends.get(fid)

    def list_all(self) -> list[dict[str, Any]]:
        return list(self._frontends.values())

    def list_enabled(self) -> list[dict[str, Any]]:
        return [f for f in self._frontends.values() if f["enabled"]]


registry = FrontendRegistry()
