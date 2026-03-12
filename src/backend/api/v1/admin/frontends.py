import asyncio
import json
import logging
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from src.api.v1.admin.auth import require_admin
from src.services.frontend_registry import registry
from src.services.prompt_assembler import get_prompt_mode, copy_global_to_frontend

logger = logging.getLogger("backend.admin.frontends")
_CAMPAIGNS_DIR = Path("/app/data/campaigns")

router = APIRouter(prefix="/admin/frontends", tags=["admin-frontends"])


class RegisterRequest(BaseModel):
    url: str
    name: str = ""


class UpdateRequest(BaseModel):
    enabled: bool | None = None
    name: str | None = None


@router.get("")
async def list_frontends(_: dict = Depends(require_admin)):
    return {"frontends": registry.list_all()}


@router.post("")
async def register_frontend(req: RegisterRequest, _: dict = Depends(require_admin)):
    """Register a frontend by URL. Auto-discovers type via GET /internal/config."""
    url = req.url.rstrip("/")

    # Discover frontend config
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{url}/internal/config")
            resp.raise_for_status()
            config = resp.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Cannot reach frontend at {url}: {str(e)}")

    frontend_type = config.get("frontend_type", "worker")
    frontend = registry.register(url, frontend_type, req.name)
    registry.set_status(frontend["id"], "online")

    # Auto-copy global prompts if in per_frontend mode (Sprint 8h loose end)
    if get_prompt_mode() == "per_frontend":
        copied = copy_global_to_frontend(frontend["id"])
        if copied:
            frontend["prompts_copied"] = copied

    return {"frontend": frontend}


@router.put("/{frontend_id}")
async def update_frontend(frontend_id: str, req: UpdateRequest, _: dict = Depends(require_admin)):
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    frontend = registry.update(frontend_id, **updates)
    if not frontend:
        raise HTTPException(status_code=404, detail="Frontend not found")
    return {"frontend": frontend}


@router.delete("/{frontend_id}")
async def remove_frontend(frontend_id: str, _: dict = Depends(require_admin)):
    if not registry.remove(frontend_id):
        raise HTTPException(status_code=404, detail="Frontend not found")
    return {"status": "removed"}


# --- Branding ---

class BrandingRequest(BaseModel):
    app_title: str = ""
    logo_url: str = ""
    disclaimer_text: str = ""
    instructions_text: str = ""


def _branding_path(frontend_id: str) -> Path:
    return _CAMPAIGNS_DIR / frontend_id / "branding.json"


@router.get("/{frontend_id}/branding")
async def get_branding(frontend_id: str, _: dict = Depends(require_admin)):
    path = _branding_path(frontend_id)
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {"app_title": "", "logo_url": "", "disclaimer_text": "", "instructions_text": ""}


@router.put("/{frontend_id}/branding")
async def update_branding(frontend_id: str, req: BrandingRequest, _: dict = Depends(require_admin)):
    """Save branding config. If custom text is set, trigger LLM translation in background."""
    from src.services.branding_translator import translate_branding, delete_translations, load_translations
    from src.services.polling import invalidate_branding_cache

    data = req.model_dump()
    # Save to disk
    path = _branding_path(frontend_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.rename(path)
    logger.info(f"Branding saved for frontend {frontend_id}")

    has_custom_text = bool(data.get("disclaimer_text") or data.get("instructions_text"))

    if has_custom_text:
        # Launch background translation
        async def _safe_translate():
            try:
                await translate_branding(frontend_id, data)
                # Push branding + translations to sidecar after translation completes
                await _push_branding_to_sidecar(frontend_id)
            except Exception as e:
                logger.error(f"Background translation failed for {frontend_id}: {e}")

        asyncio.create_task(_safe_translate())
        translation_status = "translating"
    else:
        # Reset to default — delete translations and push empty branding
        delete_translations(frontend_id)
        translation_status = "idle"

    # Push base branding immediately (without translations)
    invalidate_branding_cache(frontend_id)
    await _push_branding_to_sidecar(frontend_id)

    return {**data, "translation_status": translation_status}


async def _push_branding_to_sidecar(frontend_id: str):
    """Push branding config + translations to the sidecar."""
    from src.services.branding_translator import load_translations

    path = _branding_path(frontend_id)
    if not path.exists():
        return

    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return

    # Include translations if available
    translations = load_translations(frontend_id)
    has_custom_text = bool(data.get("disclaimer_text") or data.get("instructions_text"))
    payload = {
        **data,
        "custom": has_custom_text,
        "translations": translations,
    }

    fe = registry.get(frontend_id)
    if fe and fe.get("enabled"):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(f"{fe['url']}/internal/branding", json=payload)
                logger.info(f"Branding pushed to {fe['url']}")
        except Exception as e:
            logger.warning(f"Failed to push branding to {fe['url']}: {e}")


@router.get("/{frontend_id}/branding/translation-status")
async def get_branding_translation_status(frontend_id: str, _: dict = Depends(require_admin)):
    """Get the current translation status for a frontend's branding."""
    from src.services.branding_translator import get_translation_status
    return get_translation_status(frontend_id)
