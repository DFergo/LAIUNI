"""Admin LLM endpoints — connections, health, models, slot config.

Sprint 19: slots reference a (connection, model) pair from the connection
registry instead of a raw provider string. Parameters are optional overrides
(sent only when set). Existing settings migrate on load.
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.api.v1.admin.auth import require_admin
from src.core.config import config
from src.core.paths import LLM_SETTINGS, PROMPTS_DIR, CAMPAIGNS_DIR
from src.services.connection_registry import connections
from src.services.llm_provider import llm

logger = logging.getLogger("backend.admin.llm")

router = APIRouter(prefix="/admin/llm", tags=["admin-llm"])

# LLM settings persist under DATA_DIR/config/ (Sprint 24 layout)
_SETTINGS_PATH = LLM_SETTINGS

_SLOT_PREFIXES = ["inference", "reporter", "summariser", "translation"]

# Sprint 19 migration: old {slot}_provider strings → seeded connection IDs.
_PROVIDER_TO_CONNECTION = {"ollama": "ollama-default", "lm_studio": "lmstudio-default"}


# Params default to None → provider default applies (Sprint 19, Block D).
_DEFAULTS: dict[str, Any] = {
    "inference_connection": "lmstudio-default",
    "inference_model": config.lm_studio_model,
    "inference_temperature": None,
    "inference_max_tokens": None,
    "inference_num_ctx": None,
    "inference_reasoning": None,  # None = provider default; off|low|medium|high
    "reporter_connection": "lmstudio-default",
    "reporter_model": config.lm_studio_model,
    "reporter_temperature": None,
    "reporter_max_tokens": None,
    "reporter_num_ctx": None,
    "reporter_reasoning": None,  # None = provider default; off|low|medium|high
    "use_reporter_for_user_summary": False,
    "multimodal_enabled": False,
    # Sprint 40: keep each turn's knowledge-base excerpts in the chat context
    # (append-only prompt → provider prompt-cache hits; the model keeps what it
    # already used). Off = excerpts for the current turn only.
    "keep_rag_context": True,
    "summariser_enabled": False,
    "summariser_connection": "ollama-default",
    "summariser_model": config.ollama_summariser_model,
    "summariser_temperature": None,
    "summariser_max_tokens": None,
    "summariser_num_ctx": None,
    "summariser_reasoning": None,  # None = provider default; off|low|medium|high
    "translation_connection": "lmstudio-default",
    "translation_model": config.lm_studio_model,
    "translation_temperature": None,
    "translation_max_tokens": None,
    "translation_num_ctx": None,
    "translation_reasoning": None,  # None = provider default; off|low|medium|high
    "translation_glossary_enabled": False,
    # Embedding slot (RAG). None → local sentence-transformers fallback (CPU,
    # baked into the image, unchanged default behaviour). Set both to route
    # embeddings through a connection instead (network/GPU, far faster on
    # RAG-heavy responses — see connection_registry.py).
    "embedding_connection": None,
    "embedding_model": None,
    "compression_threshold": 0.75,  # legacy — kept for migration
    "compression_first_threshold": 20000,  # first compression at N tokens
    "compression_step_size": 15000,  # compress again every N tokens after first
    # Sprint 26 — concurrency (per-frontend override via the merge below).
    # 1 = sequential (one chat turn at a time); raise for parallel sessions.
    "max_concurrent_sessions": 1,
    # Sprint 26 — optional global inference fallback (e.g. commercial → local).
    "inference_fallback_enabled": False,
    "inference_fallback_connection": None,
    "inference_fallback_model": None,
    "inference_fallback_temperature": None,
    "inference_fallback_max_tokens": None,
    "inference_fallback_num_ctx": None,
    "inference_fallback_reasoning": None,  # None = provider default; off|low|medium|high
}


def _migrate_provider_keys(data: dict[str, Any]) -> dict[str, Any]:
    """Migrate legacy `{slot}_provider` strings to `{slot}_connection` IDs.

    Idempotent: only migrates when a provider key exists and its connection
    counterpart does not. Preserves existing model/param values (so a migrated
    production keeps its num_ctx etc.).
    """
    # Even-older flat format (single temperature/max_tokens/num_ctx)
    if "temperature" in data and "inference_temperature" not in data:
        data["inference_temperature"] = data.pop("temperature", None)
        data["inference_max_tokens"] = data.pop("max_tokens", None)
        data["summariser_num_ctx"] = data.pop("num_ctx", None)
    for slot in _SLOT_PREFIXES:
        prov_key = f"{slot}_provider"
        conn_key = f"{slot}_connection"
        if prov_key in data:
            prov = data.pop(prov_key)
            data.setdefault(conn_key, _PROVIDER_TO_CONNECTION.get(prov, "lmstudio-default"))
    return data


def _load_settings() -> dict[str, Any]:
    if _SETTINGS_PATH.exists():
        try:
            data = json.loads(_SETTINGS_PATH.read_text())
        except (json.JSONDecodeError, OSError) as e:
            # §0.7: reject-with-log, don't crash on a malformed structured file
            logger.error(f"Malformed llm_settings.json rejected, using defaults: {e}")
            return dict(_DEFAULTS)
        data = _migrate_provider_keys(data)
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
    fe_path = CAMPAIGNS_DIR / frontend_id / "llm_settings.json"
    if not fe_path.exists():
        return global_settings
    try:
        override = _migrate_provider_keys(json.loads(fe_path.read_text()))
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
    fe_path = CAMPAIGNS_DIR / frontend_id / "llm_settings.json"
    if fe_path.exists():
        try:
            return _migrate_provider_keys(json.loads(fe_path.read_text()))
        except Exception:
            pass
    return {}


def save_frontend_llm_override(frontend_id: str, override: dict[str, Any]):
    """Save per-frontend LLM override."""
    campaign_dir = CAMPAIGNS_DIR / frontend_id
    campaign_dir.mkdir(parents=True, exist_ok=True)
    fe_path = campaign_dir / "llm_settings.json"
    tmp = fe_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(override, indent=2))
    tmp.rename(fe_path)


def delete_frontend_llm_override(frontend_id: str):
    """Remove per-frontend LLM override (revert to global)."""
    fe_path = CAMPAIGNS_DIR / frontend_id / "llm_settings.json"
    if fe_path.exists():
        fe_path.unlink()


async def _warmup_ollama_slots(settings: dict[str, Any]):
    """Pre-load Ollama models into VRAM for slots whose connection is ollama-type.

    Sprint 19: warmup fires per (connection, model), gated on the connection's
    type. Runs as a background task after config save. Silently logs failures.
    """
    for slot in _SLOT_PREFIXES:
        conn_id = settings.get(f"{slot}_connection", "")
        model = settings.get(f"{slot}_model", "")
        conn = connections.get(conn_id)
        if not conn or conn.get("type") != "ollama" or not model:
            continue
        try:
            await llm.warmup(conn_id, model)
            logger.info(f"Ollama warmup OK: {slot} → {conn_id}/{model}")
        except Exception as e:
            logger.warning(f"Ollama warmup failed for {slot} ({conn_id}/{model}): {e}")


def _has_ollama_slot(settings: dict[str, Any]) -> bool:
    for slot in _SLOT_PREFIXES:
        conn = connections.get(settings.get(f"{slot}_connection", ""))
        if conn and conn.get("type") == "ollama":
            return True
    return False


def _check_reasoning(updates: dict[str, Any]):
    from src.services.llm_capabilities import REASONING_LEVELS
    for key, val in updates.items():
        if key.endswith("_reasoning") and val not in (None, "", *REASONING_LEVELS):
            raise HTTPException(status_code=400, detail=f"{key} must be one of: default, {', '.join(REASONING_LEVELS)}")
        if key.endswith("_reasoning") and val == "":
            updates[key] = None


class LLMSettingsRequest(BaseModel):
    inference_connection: str | None = None
    inference_model: str | None = None
    inference_temperature: float | None = None
    inference_max_tokens: int | None = None
    inference_num_ctx: int | None = None
    inference_reasoning: str | None = None
    reporter_connection: str | None = None
    reporter_model: str | None = None
    reporter_temperature: float | None = None
    reporter_max_tokens: int | None = None
    reporter_num_ctx: int | None = None
    reporter_reasoning: str | None = None
    use_reporter_for_user_summary: bool | None = None
    multimodal_enabled: bool | None = None
    keep_rag_context: bool | None = None
    summariser_enabled: bool | None = None
    summariser_connection: str | None = None
    summariser_model: str | None = None
    summariser_temperature: float | None = None
    summariser_max_tokens: int | None = None
    summariser_num_ctx: int | None = None
    summariser_reasoning: str | None = None
    translation_connection: str | None = None
    translation_model: str | None = None
    translation_temperature: float | None = None
    translation_max_tokens: int | None = None
    translation_num_ctx: int | None = None
    translation_reasoning: str | None = None
    translation_glossary_enabled: bool | None = None
    embedding_connection: str | None = None
    embedding_model: str | None = None
    compression_threshold: float | None = None  # legacy
    compression_first_threshold: int | None = None
    compression_step_size: int | None = None
    # Sprint 26
    max_concurrent_sessions: int | None = None
    inference_fallback_enabled: bool | None = None
    inference_fallback_connection: str | None = None
    inference_fallback_model: str | None = None
    inference_fallback_temperature: float | None = None
    inference_fallback_max_tokens: int | None = None
    inference_fallback_num_ctx: int | None = None
    inference_fallback_reasoning: str | None = None


class ConnectionRequest(BaseModel):
    id: str | None = None
    type: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    prefix_id: str | None = None
    model_ids: list[str] | None = None
    enable: bool | None = None
    provider: str | None = None          # "" = infer from base_url
    prompt_cache_key: bool | None = None
    routing: dict[str, Any] | None = None


# --- Connections registry ---


@router.get("/connections")
async def list_connections(_: dict = Depends(require_admin)):
    """List all provider connections."""
    return {"connections": connections.all()}


@router.post("/connections")
async def add_connection(req: ConnectionRequest, _: dict = Depends(require_admin)):
    """Add a provider connection."""
    try:
        return connections.add(req.model_dump(exclude_none=True))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/connections/{connection_id}")
async def update_connection(connection_id: str, req: ConnectionRequest, _: dict = Depends(require_admin)):
    """Update a provider connection."""
    try:
        return connections.update(connection_id, req.model_dump(exclude_unset=True))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/connections/{connection_id}")
async def remove_connection(connection_id: str, _: dict = Depends(require_admin)):
    """Delete a provider connection."""
    connections.delete(connection_id)
    return {"deleted": connection_id}


@router.get("/connections/{connection_id}/models")
async def connection_models(connection_id: str, _: dict = Depends(require_admin)):
    """Fetch a connection's models (async, short timeout). Never blocks the UI.

    Model discovery is decoupled from usability: if this fails the admin can
    still type a model ID manually.
    """
    conn = connections.get(connection_id)
    if not conn:
        raise HTTPException(status_code=404, detail=f"Connection not found: {connection_id}")
    result = await llm.check_connection(conn)
    return {"connection_id": connection_id, **result}


# --- Health / models ---


@router.get("/health")
async def llm_health(_: dict = Depends(require_admin)):
    """Health of all enabled connections + per-slot circuit breaker state."""
    return {
        "connections": await llm.check_health(),
        "slot_health": llm.get_slot_health(),
    }


@router.get("/models")
async def llm_models(_: dict = Depends(require_admin)):
    """Get available models per enabled connection."""
    return {"connections": await llm.check_health()}


@router.get("/embedding-health")
async def llm_embedding_health(_: dict = Depends(require_admin)):
    """Embedding-only models per enabled connection, for the embedding slot's dropdown."""
    return {"connections": await llm.check_embedding_health()}


@router.get("/connections/{connection_id}/embedding-models")
async def connection_embedding_models(connection_id: str, _: dict = Depends(require_admin)):
    """Fetch a connection's embedding-only models (async, short timeout)."""
    conn = connections.get(connection_id)
    if not conn:
        raise HTTPException(status_code=404, detail=f"Connection not found: {connection_id}")
    result = await llm.check_embedding_connection(conn)
    return {"connection_id": connection_id, **result}


# --- Settings ---


@router.get("/settings")
async def get_settings(_: dict = Depends(require_admin)):
    """Get current LLM settings."""
    return _load_settings()


@router.put("/settings")
async def update_settings(req: LLMSettingsRequest, _: dict = Depends(require_admin)):
    """Update LLM settings.

    Uses ``exclude_unset`` so an explicitly-sent ``null`` clears a parameter
    override (blank → provider default), while omitted fields are untouched.
    """
    current = _load_settings()
    updates = req.model_dump(exclude_unset=True)
    _check_reasoning(updates)
    current.update(updates)
    _save_settings(current)
    logger.info(f"LLM settings updated: {list(updates.keys())}")

    if _has_ollama_slot(current):
        asyncio.create_task(_warmup_ollama_slots(current))

    return current


class CapabilitiesRequest(BaseModel):
    connection: str
    model: str = ""
    temperature: float | None = None
    max_tokens: int | None = None
    num_ctx: int | None = None
    reasoning: str | None = None


@router.post("/capabilities")
async def slot_capabilities(req: CapabilitiesRequest, _: dict = Depends(require_admin)):
    """Which of a slot's controls are sent, renamed or ignored on this
    connection + model (Sprint 37) — so the admin never shows a silent no-op.
    Takes the values being edited (not only the saved ones)."""
    from src.services import llm_capabilities
    conn = connections.get(req.connection)
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    info = await llm.model_info(req.connection, req.model) if req.model else {}
    out = llm_capabilities.describe(conn, req.model, req.model_dump(), info.get("supported_parameters"))
    out["context_length"] = info.get("context_length")
    return out


@router.get("/usage")
async def llm_usage_summary(_: dict = Depends(require_admin)):
    """Token and prompt-cache usage per slot/connection/model since the last reset."""
    from src.services import llm_usage
    return {"rows": llm_usage.global_summary()}


@router.post("/usage/reset")
async def llm_usage_reset(_: dict = Depends(require_admin)):
    from src.services import llm_usage
    llm_usage.reset_global()
    return {"rows": []}


@router.post("/embedding/reindex")
async def reindex_embedding(_: dict = Depends(require_admin)):
    """Activate the saved embedding slot everywhere — global RAG AND every
    campaign (per-frontend) index (Sprint 34).

    Dedicated action — never triggered by saving settings. The old embedding
    model + every index keep serving requests until this runs. The embedding
    model is a single global setting shared by all indexes (a campaign's
    `include_global_rag` toggle doesn't give it its own embedding space), so
    a provider switch must reindex all of them together, not just the global
    one. Reuses a previously-built index for the same (connection, model) per
    index if one exists; only a genuinely new pairing costs a rebuild.
    """
    from src.services.rag_service import switch_embedding_and_reindex
    return switch_embedding_and_reindex()


@router.post("/settings/reset")
async def reset_settings(_: dict = Depends(require_admin)):
    """Reset LLM settings to defaults."""
    _save_settings(dict(_DEFAULTS))
    logger.info("LLM settings reset to defaults")
    return dict(_DEFAULTS)


# --- Translation prompt (Sprint 20; disk source-of-truth per REFACTOR §0.7) ---

_TRANSLATE_PROMPT_PATH = PROMPTS_DIR / "translate.md"
_TRANSLATE_PROMPT_BUNDLED = Path(__file__).parent.parent.parent.parent / "prompts" / "translate.md"


def load_translation_prompt() -> str:
    """Effective translation prompt: disk override if present, else bundled default."""
    if _TRANSLATE_PROMPT_PATH.exists():
        try:
            return _TRANSLATE_PROMPT_PATH.read_text()
        except OSError:
            pass
    if _TRANSLATE_PROMPT_BUNDLED.exists():
        return _TRANSLATE_PROMPT_BUNDLED.read_text()
    return "You are a professional translator. Translate the text accurately. Return only the translation."


class TranslationPromptRequest(BaseModel):
    prompt: str


@router.get("/translation-prompt")
async def get_translation_prompt(_: dict = Depends(require_admin)):
    """Get the editable translation prompt (effective text)."""
    return {"prompt": load_translation_prompt()}


@router.put("/translation-prompt")
async def update_translation_prompt(req: TranslationPromptRequest, _: dict = Depends(require_admin)):
    """Save the translation prompt to disk (atomic)."""
    _TRANSLATE_PROMPT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _TRANSLATE_PROMPT_PATH.with_suffix(".md.tmp")
    tmp.write_text(req.prompt)
    tmp.rename(_TRANSLATE_PROMPT_PATH)
    logger.info("Translation prompt updated")
    return {"prompt": req.prompt}


# --- Per-frontend LLM overrides ---

fe_router = APIRouter(prefix="/admin/frontends", tags=["admin-frontend-llm"])


@fe_router.get("/{frontend_id}/llm-settings")
async def get_fe_llm_settings(frontend_id: str, _: dict = Depends(require_admin)):
    """Get per-frontend LLM override."""
    return {"frontend_id": frontend_id, "override": get_frontend_llm_override(frontend_id)}


@fe_router.put("/{frontend_id}/llm-settings")
async def update_fe_llm_settings(frontend_id: str, req: LLMSettingsRequest, _: dict = Depends(require_admin)):
    """Update per-frontend LLM override. Only set fields are stored."""
    override = req.model_dump(exclude_unset=True)
    if override:
        save_frontend_llm_override(frontend_id, override)
        logger.info(f"Per-frontend LLM override saved for {frontend_id}: {list(override.keys())}")

        merged = get_llm_settings(frontend_id)
        if _has_ollama_slot(merged):
            asyncio.create_task(_warmup_ollama_slots(merged))

    return {"frontend_id": frontend_id, "override": override}


@fe_router.delete("/{frontend_id}/llm-settings")
async def delete_fe_llm_settings(frontend_id: str, _: dict = Depends(require_admin)):
    """Remove per-frontend LLM override (revert to global)."""
    delete_frontend_llm_override(frontend_id)
    logger.info(f"Per-frontend LLM override removed for {frontend_id}")
    return {"frontend_id": frontend_id, "override": {}}
