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


def _load_settings() -> dict[str, Any]:
    if _SETTINGS_PATH.exists():
        return json.loads(_SETTINGS_PATH.read_text())
    return {
        "inference_provider": "lm_studio",
        "inference_model": config.lm_studio_model,
        "summariser_provider": "ollama",
        "summariser_model": config.ollama_summariser_model,
        "temperature": 0.7,
        "max_tokens": 2048,
        "num_ctx": config.ollama_num_ctx,
    }


def _save_settings(settings: dict[str, Any]):
    tmp = _SETTINGS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(settings, indent=2))
    tmp.rename(_SETTINGS_PATH)


def get_llm_settings() -> dict[str, Any]:
    """Get current LLM settings (used by other services)."""
    return _load_settings()


class LLMSettingsRequest(BaseModel):
    inference_provider: str | None = None
    inference_model: str | None = None
    summariser_provider: str | None = None
    summariser_model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    num_ctx: int | None = None


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
