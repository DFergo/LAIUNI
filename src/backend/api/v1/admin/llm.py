"""Admin LLM endpoints — health, models, config."""

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.api.v1.admin.auth import require_admin
from src.core.config import config
from src.services.llm_provider import llm

logger = logging.getLogger("backend.admin.llm")

router = APIRouter(prefix="/admin/llm", tags=["admin-llm"])

# LLM settings persist to /app/data/llm_settings.json
_SETTINGS_PATH = Path("/app/data/llm_settings.json")


_DEFAULTS = {
    "inference_provider": "lm_studio",
    "inference_model": config.lm_studio_model,
    "inference_temperature": 0.7,
    "inference_max_tokens": 2048,
    "inference_num_ctx": 32768,
    "summariser_enabled": False,
    "summariser_provider": "ollama",
    "summariser_model": config.ollama_summariser_model,
    "summariser_temperature": 0.3,
    "summariser_max_tokens": 1024,
    "summariser_num_ctx": config.ollama_num_ctx,
    "compression_threshold": 0.75,  # legacy — kept for migration
    "compression_first_threshold": 20000,  # first compression at N tokens
    "compression_step_size": 15000,  # compress again every N tokens after first
}


def _load_settings() -> dict[str, Any]:
    if _SETTINGS_PATH.exists():
        data = json.loads(_SETTINGS_PATH.read_text())
        # Migrate old flat format to per-slot format
        if "temperature" in data and "inference_temperature" not in data:
            data["inference_temperature"] = data.pop("temperature", 0.7)
            data["inference_max_tokens"] = data.pop("max_tokens", 2048)
            data["summariser_temperature"] = 0.3
            data["summariser_max_tokens"] = 1024
            data["summariser_num_ctx"] = data.pop("num_ctx", config.ollama_num_ctx)
        # Ensure all keys exist (new fields added over time)
        for key, val in _DEFAULTS.items():
            data.setdefault(key, val)
        return data
    return dict(_DEFAULTS)


def _save_settings(settings: dict[str, Any]):
    tmp = _SETTINGS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(settings, indent=2))
    tmp.rename(_SETTINGS_PATH)


def get_llm_settings(frontend_id: str = "") -> dict[str, Any]:
    """Get LLM settings — per-frontend override if exists, else global."""
    global_settings = _load_settings()
    if not frontend_id:
        return global_settings
    fe_path = Path(f"/app/data/campaigns/{frontend_id}/llm_settings.json")
    if not fe_path.exists():
        return global_settings
    try:
        override = json.loads(fe_path.read_text())
        # Merge: override only non-null fields on top of global
        merged = dict(global_settings)
        for key, val in override.items():
            if val is not None:
                merged[key] = val
        return merged
    except Exception as e:
        logger.warning(f"Failed to load per-frontend LLM settings for {frontend_id}: {e}")
        return global_settings


def get_frontend_llm_override(frontend_id: str) -> dict[str, Any]:
    """Get raw per-frontend LLM override (only overridden fields)."""
    fe_path = Path(f"/app/data/campaigns/{frontend_id}/llm_settings.json")
    if fe_path.exists():
        try:
            return json.loads(fe_path.read_text())
        except Exception:
            pass
    return {}


def save_frontend_llm_override(frontend_id: str, override: dict[str, Any]):
    """Save per-frontend LLM override."""
    campaign_dir = Path(f"/app/data/campaigns/{frontend_id}")
    campaign_dir.mkdir(parents=True, exist_ok=True)
    fe_path = campaign_dir / "llm_settings.json"
    tmp = fe_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(override, indent=2))
    tmp.rename(fe_path)


def delete_frontend_llm_override(frontend_id: str):
    """Remove per-frontend LLM override (revert to global)."""
    fe_path = Path(f"/app/data/campaigns/{frontend_id}/llm_settings.json")
    if fe_path.exists():
        fe_path.unlink()


class LLMSettingsRequest(BaseModel):
    inference_provider: str | None = None
    inference_model: str | None = None
    inference_temperature: float | None = None
    inference_max_tokens: int | None = None
    inference_num_ctx: int | None = None
    summariser_enabled: bool | None = None
    summariser_provider: str | None = None
    summariser_model: str | None = None
    summariser_temperature: float | None = None
    summariser_max_tokens: int | None = None
    summariser_num_ctx: int | None = None
    compression_threshold: float | None = None  # legacy
    compression_first_threshold: int | None = None
    compression_step_size: int | None = None


@router.get("/health")
async def llm_health(_: dict = Depends(require_admin)):
    """Check LLM provider health status."""
    health = await llm.check_health()
    return health


@router.get("/models")
async def llm_models(_: dict = Depends(require_admin)):
    """Get available models from both providers."""
    health = await llm.check_health()
    return {
        "lm_studio": {
            "status": health["lm_studio"]["status"],
            "models": health["lm_studio"].get("models", []),
        },
        "ollama": {
            "status": health["ollama"]["status"],
            "models": health["ollama"].get("models", []),
        },
    }


@router.get("/settings")
async def get_settings(_: dict = Depends(require_admin)):
    """Get current LLM settings."""
    return _load_settings()


@router.put("/settings")
async def update_settings(req: LLMSettingsRequest, _: dict = Depends(require_admin)):
    """Update LLM settings."""
    current = _load_settings()
    updates = req.model_dump(exclude_none=True)
    current.update(updates)
    _save_settings(current)
    logger.info(f"LLM settings updated: {list(updates.keys())}")
    return current


@router.post("/settings/reset")
async def reset_settings(_: dict = Depends(require_admin)):
    """Reset LLM settings to defaults."""
    _save_settings(dict(_DEFAULTS))
    logger.info("LLM settings reset to defaults")
    return dict(_DEFAULTS)


# --- Per-frontend LLM overrides ---

fe_router = APIRouter(prefix="/admin/frontends", tags=["admin-frontend-llm"])


@fe_router.get("/{frontend_id}/llm-settings")
async def get_fe_llm_settings(frontend_id: str, _: dict = Depends(require_admin)):
    """Get per-frontend LLM override."""
    return {"frontend_id": frontend_id, "override": get_frontend_llm_override(frontend_id)}


@fe_router.put("/{frontend_id}/llm-settings")
async def update_fe_llm_settings(frontend_id: str, req: LLMSettingsRequest, _: dict = Depends(require_admin)):
    """Update per-frontend LLM override. Only non-null fields are stored."""
    override = req.model_dump(exclude_none=True)
    if override:
        save_frontend_llm_override(frontend_id, override)
        logger.info(f"Per-frontend LLM override saved for {frontend_id}: {list(override.keys())}")
    return {"frontend_id": frontend_id, "override": override}


@fe_router.delete("/{frontend_id}/llm-settings")
async def delete_fe_llm_settings(frontend_id: str, _: dict = Depends(require_admin)):
    """Remove per-frontend LLM override (revert to global)."""
    delete_frontend_llm_override(frontend_id)
    logger.info(f"Per-frontend LLM override removed for {frontend_id}")
    return {"frontend_id": frontend_id, "override": {}}
