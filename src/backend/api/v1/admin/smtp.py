"""Admin SMTP endpoints — config, test connection."""

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.api.v1.admin.auth import require_admin

logger = logging.getLogger("backend.admin.smtp")

router = APIRouter(prefix="/admin/smtp", tags=["admin-smtp"])

_SETTINGS_PATH = Path("/app/data/smtp_config.json")

_DEFAULTS = {
    "host": "",
    "port": 587,
    "username": "",
    "password": "",
    "use_tls": True,
    "from_address": "",
    "admin_notify_address": "",
}


def _load_config() -> dict[str, Any]:
    if _SETTINGS_PATH.exists():
        data = json.loads(_SETTINGS_PATH.read_text())
        for key, val in _DEFAULTS.items():
            data.setdefault(key, val)
        return data
    return dict(_DEFAULTS)


def _save_config(config: dict[str, Any]):
    tmp = _SETTINGS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(config, indent=2))
    tmp.rename(_SETTINGS_PATH)


class SMTPConfigRequest(BaseModel):
    host: str | None = None
    port: int | None = None
    username: str | None = None
    password: str | None = None
    use_tls: bool | None = None
    from_address: str | None = None
    admin_notify_address: str | None = None


@router.get("")
async def get_smtp_config(_: dict = Depends(require_admin)):
    """Get current SMTP configuration."""
    cfg = _load_config()
    # Mask password in response
    if cfg.get("password"):
        cfg["password"] = "••••••••"
    return cfg


@router.put("")
async def update_smtp_config(req: SMTPConfigRequest, _: dict = Depends(require_admin)):
    """Update SMTP configuration."""
    current = _load_config()
    updates = req.model_dump(exclude_none=True)
    # Don't overwrite password with masked value
    if updates.get("password") == "••••••••":
        del updates["password"]
    current.update(updates)
    _save_config(current)
    logger.info(f"SMTP config updated: {list(updates.keys())}")
    # Return with masked password
    if current.get("password"):
        current["password"] = "••••••••"
    return current


@router.post("/test")
async def test_smtp(_: dict = Depends(require_admin)):
    """Test SMTP connection (stub — actual implementation in Sprint 9)."""
    cfg = _load_config()
    if not cfg.get("host"):
        return {"status": "error", "message": "SMTP host not configured"}
    # Stub — real test in Sprint 9
    return {"status": "not_implemented", "message": "SMTP test will be available in Sprint 9"}
