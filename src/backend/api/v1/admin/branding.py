"""Global branding (Sprint 43, docs/BRANDING-TOKENS.md).

The organization's name, the tool's name, the colours and the logos, for every
frontend by default. A frontend can override any token (PUT /admin/frontends/{id}/branding).
"""

import io
import logging
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from src.api.v1.admin.auth import require_admin
from src.services import branding_tokens as bt

logger = logging.getLogger("backend.admin.branding")

router = APIRouter(prefix="/admin/branding", tags=["admin-branding"])


class GlobalBrandingRequest(BaseModel):
    # token → value. An empty value removes the override (the token returns to its default).
    values: dict[str, Any]


def merge_overrides(current: dict[str, str], changes: dict[str, Any]) -> dict[str, str]:
    """Apply a partial change: validated values are set, empty ones are removed."""
    try:
        valid = bt.validate(changes)
    except bt.TokenError as e:
        raise HTTPException(status_code=400, detail=str(e))
    merged = {**current, **valid}
    for name, raw in changes.items():
        if name not in valid and (raw is None or (isinstance(raw, str) and not raw.strip())):
            merged.pop(name, None)
    return merged


def republish():
    """Every frontend gets the new branding on its next poll."""
    from src.services.polling import invalidate_branding_cache
    invalidate_branding_cache()


@router.get("/public")
async def public_branding():
    """What the admin login page needs to look like the organization (no secrets, no auth)."""
    v = bt.values()
    return {k: v[k] for k in ("org_name", "org_short_name", "tool_name", "color_primary",
                              "color_on_primary", "color_accent", "color_dark")}


@router.get("")
async def get_branding(_: dict = Depends(require_admin)):
    return bt.catalog()


@router.put("")
async def update_branding(req: GlobalBrandingRequest, _: dict = Depends(require_admin)):
    bt.save_global(merge_overrides(bt.global_overrides(), req.values))
    republish()
    logger.info("Global branding updated")
    return bt.catalog()


@router.post("/reset")
async def reset_branding(_: dict = Depends(require_admin)):
    """Back to the defaults: every token override and logo of the global catalog is removed."""
    bt.save_global({})
    for slot in bt.LOGO_SLOTS:
        bt.delete_logo(None, slot)
    republish()
    return bt.catalog()


def read_logo_upload(raw: bytes, filename: str) -> tuple[bytes, bytes | None]:
    from src.api.v1.admin.frontends import _LOGO_ALLOWED, _LOGO_MAX_SIZE, _process_logo
    ext = (filename or "").rsplit(".", 1)[-1].lower()
    if ext not in _LOGO_ALLOWED:
        raise HTTPException(status_code=400, detail=f"Unsupported format. Allowed: {', '.join(sorted(_LOGO_ALLOWED))}")
    if len(raw) > _LOGO_MAX_SIZE:
        raise HTTPException(status_code=400, detail="Image too large (max 2 MB)")
    return _process_logo(raw)


@router.post("/logo/{slot}")
async def upload_logo(slot: str, file: UploadFile = File(...), _: dict = Depends(require_admin)):
    if slot not in bt.LOGO_SLOTS:
        raise HTTPException(status_code=404, detail=f"Unknown slot. Slots: {', '.join(bt.LOGO_SLOTS)}")
    color_png, white_png = read_logo_upload(await file.read(), file.filename or "")
    bt.save_logo(None, slot, color_png, white_png)
    republish()
    return bt.catalog()


@router.delete("/logo/{slot}")
async def delete_logo(slot: str, _: dict = Depends(require_admin)):
    if slot not in bt.LOGO_SLOTS:
        raise HTTPException(status_code=404, detail=f"Unknown slot. Slots: {', '.join(bt.LOGO_SLOTS)}")
    bt.delete_logo(None, slot)
    republish()
    return bt.catalog()


@router.get("/logo/{slot}/{variant}")
async def get_logo(slot: str, variant: str, _: dict = Depends(require_admin)):
    """The global logo, for the admin preview."""
    if slot not in bt.LOGO_SLOTS or variant not in ("color", "white"):
        raise HTTPException(status_code=404, detail="Unknown logo")
    p = bt.logo_path(None, slot, variant)
    if not p.exists():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(p, media_type="image/png")
