"""Admin knowledge base endpoints — glossary and organizations directory.

These are structured JSON files read directly by the LLM (not indexed via RAG).
They provide deterministic, curated data for term consistency and organization referrals.
"""

import json
import logging
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.api.v1.admin.auth import require_admin

logger = logging.getLogger("backend.admin.knowledge")

router = APIRouter(prefix="/admin/knowledge", tags=["admin-knowledge"])

from src.core.paths import CAMPAIGNS_DIR, KNOWLEDGE_DIR as _KNOWLEDGE_DIR
_DEFAULTS_DIR = Path(__file__).parent.parent.parent.parent / "knowledge"


def _ensure_dir():
    _KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)


def _atomic_write(path: Path, data: Any):
    """Write JSON atomically using tmp+rename (lesson #5)."""
    _ensure_dir()
    fd, tmp = tempfile.mkstemp(dir=_KNOWLEDGE_DIR, suffix=".tmp")
    try:
        with open(fd, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        Path(tmp).replace(path)
    except Exception:
        Path(tmp).unlink(missing_ok=True)
        raise


def ensure_defaults():
    """Install default knowledge base files if they don't exist."""
    _ensure_dir()
    for name in ("glossary.json", "organizations.json"):
        dest = _KNOWLEDGE_DIR / name
        src = _DEFAULTS_DIR / name
        if not dest.exists() and src.exists():
            dest.write_text(src.read_text())
            logger.info(f"Installed default knowledge file: {name}")


def load_glossary() -> dict[str, Any]:
    """Load glossary for prompt injection."""
    path = _KNOWLEDGE_DIR / "glossary.json"
    if path.exists():
        return json.loads(path.read_text())
    return {"terms": []}


def load_organizations() -> dict[str, Any]:
    """Load organizations directory for prompt injection."""
    path = _KNOWLEDGE_DIR / "organizations.json"
    if path.exists():
        return json.loads(path.read_text())
    return {"organizations": []}


# --- On/off and per-frontend override ---
# Global switches in config/knowledge/settings.json. Each frontend can follow the
# global list ("global"), switch it off ("off") or use its own list ("custom"),
# stored in campaigns/{id}/knowledge.json — e.g. a campaign with two reference
# unions and three languages does not need the whole directory in every prompt.

MODES = ("global", "off", "custom")
_SETTINGS_DEFAULTS = {"glossary_enabled": True, "organizations_enabled": True}
_ITEMS = {"glossary": "terms", "organizations": "organizations"}


def load_knowledge_settings() -> dict[str, bool]:
    path = _KNOWLEDGE_DIR / "settings.json"
    data = json.loads(path.read_text()) if path.exists() else {}
    return {k: bool(data.get(k, v)) for k, v in _SETTINGS_DEFAULTS.items()}


def _frontend_path(frontend_id: str) -> Path:
    return CAMPAIGNS_DIR / frontend_id / "knowledge.json"


def load_frontend_knowledge(frontend_id: str) -> dict[str, Any]:
    path = _frontend_path(frontend_id)
    data = json.loads(path.read_text()) if path.exists() else {}
    out = {}
    for kind, key in _ITEMS.items():
        entry = data.get(kind) or {}
        mode = entry.get("mode") if entry.get("mode") in MODES else "global"
        out[kind] = {"mode": mode, key: list(entry.get(key) or [])}
    return out


def _effective(kind: str, frontend_id: str | None) -> list[dict[str, Any]]:
    key = _ITEMS[kind]
    if frontend_id:
        own = load_frontend_knowledge(frontend_id)[kind]
        if own["mode"] == "off":
            return []
        if own["mode"] == "custom":
            return own[key]
    if not load_knowledge_settings()[f"{kind}_enabled"]:
        return []
    return (load_glossary() if kind == "glossary" else load_organizations()).get(key, [])


def effective_glossary(frontend_id: str | None = None) -> list[dict[str, Any]]:
    """Glossary terms that apply to a frontend's sessions (empty = none)."""
    return _effective("glossary", frontend_id)


def effective_organizations(frontend_id: str | None = None) -> list[dict[str, Any]]:
    """Organizations that apply to a frontend's sessions (empty = none)."""
    return _effective("organizations", frontend_id)


# --- API Endpoints ---


@router.get("/glossary")
async def get_glossary(_: dict = Depends(require_admin)):
    """Get the full glossary."""
    return load_glossary()


class GlossaryUpdate(BaseModel):
    terms: list[dict[str, Any]]


@router.put("/glossary")
async def update_glossary(data: GlossaryUpdate, _: dict = Depends(require_admin)):
    """Save the full glossary."""
    payload = {"terms": data.terms}
    path = _KNOWLEDGE_DIR / "glossary.json"
    _atomic_write(path, payload)
    logger.info(f"Glossary saved ({len(data.terms)} terms)")
    return payload


@router.get("/organizations")
async def get_organizations(_: dict = Depends(require_admin)):
    """Get the organizations directory."""
    return load_organizations()


class OrganizationsUpdate(BaseModel):
    organizations: list[dict[str, Any]]


@router.put("/organizations")
async def update_organizations(data: OrganizationsUpdate, _: dict = Depends(require_admin)):
    """Save the organizations directory."""
    payload = {"organizations": data.organizations}
    path = _KNOWLEDGE_DIR / "organizations.json"
    _atomic_write(path, payload)
    logger.info(f"Organizations saved ({len(data.organizations)} entries)")
    return payload


class KnowledgeSettings(BaseModel):
    glossary_enabled: bool | None = None
    organizations_enabled: bool | None = None


@router.get("/settings")
async def get_knowledge_settings(_: dict = Depends(require_admin)):
    """Whether the global glossary and organizations are used in sessions."""
    return load_knowledge_settings()


@router.put("/settings")
async def update_knowledge_settings(data: KnowledgeSettings, _: dict = Depends(require_admin)):
    current = load_knowledge_settings()
    current.update(data.model_dump(exclude_none=True))
    _atomic_write(_KNOWLEDGE_DIR / "settings.json", current)
    logger.info(f"Knowledge settings: {current}")
    return current


class FrontendKnowledgeUpdate(BaseModel):
    mode: str
    items: list[dict[str, Any]] | None = None   # the own list (mode "custom"); None = keep the current one


def _check_frontend(frontend_id: str):
    from src.services.frontend_registry import registry
    if not registry.get(frontend_id):
        raise HTTPException(status_code=404, detail="Frontend not found")


@router.get("/frontend/{frontend_id}")
async def get_frontend_knowledge(frontend_id: str, _: dict = Depends(require_admin)):
    """A frontend's glossary/organizations mode and own lists."""
    _check_frontend(frontend_id)
    return load_frontend_knowledge(frontend_id)


@router.put("/frontend/{frontend_id}/{kind}")
async def update_frontend_knowledge(frontend_id: str, kind: str, data: FrontendKnowledgeUpdate,
                                    _: dict = Depends(require_admin)):
    """Set a frontend's mode for the glossary or the organizations: global, off or custom (own list)."""
    _check_frontend(frontend_id)
    if kind not in _ITEMS:
        raise HTTPException(status_code=404, detail="Use glossary or organizations")
    if data.mode not in MODES:
        raise HTTPException(status_code=400, detail=f"Mode must be one of: {', '.join(MODES)}")
    current = load_frontend_knowledge(frontend_id)
    key = _ITEMS[kind]
    current[kind] = {"mode": data.mode, key: data.items if data.items is not None else current[kind][key]}
    path = _frontend_path(frontend_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with open(fd, "w") as f:
        json.dump(current, f, indent=2, ensure_ascii=False)
    Path(tmp).replace(path)
    logger.info(f"Knowledge {kind} for {frontend_id}: {data.mode} ({len(current[kind][key])} entries)")
    return current
