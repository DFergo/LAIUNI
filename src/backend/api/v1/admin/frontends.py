import asyncio
import json
import logging
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from pydantic import BaseModel

from src.api.v1.admin.auth import require_admin
from src.services.frontend_registry import registry

logger = logging.getLogger("backend.admin.frontends")
_CAMPAIGNS_DIR = Path("/app/data/campaigns")

router = APIRouter(prefix="/admin/frontends", tags=["admin-frontends"])


class RegisterRequest(BaseModel):
    url: str
    name: str = ""


class UpdateRequest(BaseModel):
    enabled: bool | None = None
    name: str | None = None
    url: str | None = None


@router.get("")
async def list_frontends(_: dict = Depends(require_admin)):
    return {"frontends": registry.list_all()}


@router.post("")
async def register_frontend(req: RegisterRequest, _: dict = Depends(require_admin)):
    """Register a frontend by URL. Discovery stays URL-based (verify reachability
    via GET /internal/config); the frontend starts unconfigured (Sprint 21)."""
    url = req.url.rstrip("/")

    # Verify the frontend is reachable (URL-based detection, unchanged)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{url}/internal/config")
            resp.raise_for_status()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Cannot reach frontend at {url}: {str(e)}")

    frontend = registry.register(url, req.name)
    registry.set_status(frontend["id"], "online")

    # New frontends default to the global prompt set (Sprint 32); decouple from
    # the Prompts panel to customise or enable modules.
    return {"frontend": frontend}


# --- Deleted / restore (Sprint 21 soft-delete) ---

@router.get("/deleted")
async def list_deleted_frontends(_: dict = Depends(require_admin)):
    return {"frontends": registry.list_deleted()}


@router.post("/{frontend_id}/restore")
async def restore_frontend(frontend_id: str, _: dict = Depends(require_admin)):
    frontend = registry.restore(frontend_id)
    if not frontend:
        raise HTTPException(status_code=404, detail="Deleted frontend not found")
    return {"frontend": frontend}


# --- Per-frontend config (Sprint 21 schema; panel is Sprint 22) ---

@router.get("/{frontend_id}/config")
async def get_frontend_config(frontend_id: str, _: dict = Depends(require_admin)):
    if not registry.get(frontend_id):
        raise HTTPException(status_code=404, detail="Frontend not found")
    from src.services.frontend_registry import load_config
    return {"frontend_id": frontend_id, "config": load_config(frontend_id)}


@router.put("/{frontend_id}/config")
async def update_frontend_config(frontend_id: str, config: dict, _: dict = Depends(require_admin)):
    if not registry.get(frontend_id):
        raise HTTPException(status_code=404, detail="Frontend not found")
    from src.services.frontend_registry import save_config
    save_config(frontend_id, config)
    await _push_config_to_sidecar(frontend_id)
    return {"frontend_id": frontend_id, "config": config}


async def _push_config_to_sidecar(frontend_id: str):
    """Push the per-frontend config to the sidecar (mirror of branding push).

    Resolves the effective data_protection_email (Sprint 22): if the frontend
    leaves it blank, fall back to the SMTP `from_address`.
    """
    from src.services.frontend_registry import load_config
    fe = registry.get(frontend_id)
    if not fe or not fe.get("enabled"):
        return
    config = load_config(frontend_id)
    # Effective data-protection email: per-frontend override → SMTP dedicated
    # field → SMTP sender address. (Multi-sector deploys: a sector may own its
    # own data-protection contact.)
    if not config.get("data_protection_email"):
        try:
            from src.services.smtp_service import _load_config as _load_smtp
            smtp = _load_smtp()
            resolved = smtp.get("data_protection_email") or smtp.get("from_address", "")
            config = {**config, "data_protection_email": resolved}
        except Exception:
            pass
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(f"{fe['url']}/internal/frontend-config", json=config)
            logger.info(f"Config pushed to {fe['url']}")
    except Exception as e:
        logger.warning(f"Failed to push config to {fe['url']}: {e}")


@router.put("/{frontend_id}")
async def update_frontend(
    frontend_id: str,
    req: UpdateRequest,
    verify: bool = True,
    _: dict = Depends(require_admin),
):
    """Update a frontend's enabled/name/url.

    Editing the URL preserves the fid — so all campaign config under
    campaigns/{fid}/ (profiles, auth, branding, translations) stays intact.
    This is the reason to edit in place instead of delete + re-register, which
    would mint a new fid and lose that config. `?verify=false` skips only the
    reachability check (for the launchd reconciler); collision is always checked.
    """
    if not registry.get(frontend_id):
        raise HTTPException(status_code=404, detail="Frontend not found")

    updates = {k: v for k, v in req.model_dump().items() if v is not None}

    if "url" in updates:
        url = updates["url"].rstrip("/")  # normalise like register()
        updates["url"] = url
        # Reject collision with a *different* frontend — always, even when
        # reachability verification is skipped.
        for f in registry.list_all():
            if f["id"] != frontend_id and f["url"] == url:
                raise HTTPException(status_code=409, detail=f"URL already registered to frontend {f['id']}")
        # Verify reachability before saving (same pattern as register()). Any
        # http(s) host is accepted — IP, hostname, .local, Tailscale MagicDNS;
        # the reachability check decides, not the format.
        if verify:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(f"{url}/internal/config")
                    resp.raise_for_status()
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Cannot reach frontend at {url}: {str(e)}")

    frontend = registry.update(frontend_id, **updates)
    return {"frontend": frontend}


@router.delete("/{frontend_id}")
async def remove_frontend(frontend_id: str, _: dict = Depends(require_admin)):
    if not registry.remove(frontend_id):
        raise HTTPException(status_code=404, detail="Frontend not found")
    return {"status": "removed"}


# --- Branding ---

# Sprint 31: instructions are per-role; the disclaimer stays single (shown before role_select).
_BRANDING_ROLES = ["worker", "representative", "organizer", "officer"]


def _has_custom_branding_text(data: dict) -> bool:
    return bool(
        data.get("disclaimer_text")
        or data.get("instructions_text")
        or any(data.get(f"instructions_text_{r}") for r in _BRANDING_ROLES)
    )


class BrandingRequest(BaseModel):
    app_title: str = ""
    logo_url: str = ""
    logo_mode: str = "white"  # "white" | "color" — header rendering of the logo
    disclaimer_text: str = ""
    instructions_text: str = ""  # legacy single instructions (fallback for all roles)
    instructions_text_worker: str = ""
    instructions_text_representative: str = ""
    instructions_text_organizer: str = ""
    instructions_text_officer: str = ""


def _branding_path(frontend_id: str) -> Path:
    return _CAMPAIGNS_DIR / frontend_id / "branding.json"


@router.get("/{frontend_id}/branding")
async def get_branding(frontend_id: str, _: dict = Depends(require_admin)):
    path = _branding_path(frontend_id)
    if path.exists():
        try:
            data = json.loads(path.read_text())
            # Fill logo defaults for branding.json written before Sprint 33
            data.setdefault("logo_mode", "white")
            data.setdefault("logo_uploaded", False)
            data.setdefault("logo_has_white", False)
            return data
        except (json.JSONDecodeError, OSError):
            pass
    return {"app_title": "", "logo_url": "", "logo_mode": "white",
            "logo_uploaded": False, "logo_has_white": False,
            "disclaimer_text": "", "instructions_text": "",
            "instructions_text_worker": "", "instructions_text_representative": "",
            "instructions_text_organizer": "", "instructions_text_officer": ""}


@router.put("/{frontend_id}/branding")
async def update_branding(frontend_id: str, req: BrandingRequest, _: dict = Depends(require_admin)):
    """Save branding config. If custom text is set, trigger LLM translation in background."""
    from src.services.branding_translator import translate_branding, delete_translations, load_translations
    from src.services.polling import invalidate_branding_cache

    data = req.model_dump()
    # Save to disk
    path = _branding_path(frontend_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Preserve server-managed logo flags (set by the upload endpoint, not the admin form)
    if path.exists():
        try:
            prev = json.loads(path.read_text())
            data["logo_uploaded"] = prev.get("logo_uploaded", False)
            data["logo_has_white"] = prev.get("logo_has_white", False)
        except (json.JSONDecodeError, OSError):
            pass
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.rename(path)
    logger.info(f"Branding saved for frontend {frontend_id}")

    # Push the logo (mode may have changed via the toggle) alongside text branding
    await _push_logo_to_sidecar(frontend_id)

    has_custom_text = _has_custom_branding_text(data)

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
    has_custom_text = _has_custom_branding_text(data)
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


@router.post("/{frontend_id}/branding/retranslate")
async def retranslate_branding(frontend_id: str, _: dict = Depends(require_admin)):
    """Force a full re-translation from the current English source (overwrites all).

    The normal branding save fills only missing languages; this button is the
    escape hatch for "I changed the English text, regenerate everything".
    """
    from src.services.branding_translator import translate_branding

    path = _branding_path(frontend_id)
    if not path.exists():
        return {"translation_status": "idle"}
    data = json.loads(path.read_text())
    if not _has_custom_branding_text(data):
        return {"translation_status": "idle"}

    async def _safe_translate():
        try:
            await translate_branding(frontend_id, data, force=True)
            await _push_branding_to_sidecar(frontend_id)
        except Exception as e:
            logger.error(f"Force re-translation failed for {frontend_id}: {e}")

    asyncio.create_task(_safe_translate())
    return {"translation_status": "translating"}


# --- Logo upload + processing (Sprint 33) ---

_LOGO_ALLOWED = {"png", "webp", "jpg", "jpeg"}
_LOGO_MAX_SIZE = 2 * 1024 * 1024  # 2 MB
_LOGO_MAX_HEIGHT = 240  # px — covers retina of the largest use (language page h-28 ≈ 112px)


def _logo_dir(frontend_id: str) -> Path:
    return _CAMPAIGNS_DIR / frontend_id


def _process_logo(raw: bytes) -> tuple[bytes, bytes | None]:
    """Normalise an uploaded logo. Returns (color_png, white_png_or_None).

    The white variant is produced only when the image has real transparency —
    a JPG (or a flat PNG/WEBP) has none, so it renders in colour everywhere.
    """
    import io
    from PIL import Image

    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid or unreadable image file")

    img = img.convert("RGBA")
    # Downscale (keep aspect) so the pushed asset stays small; CSS handles final sizing
    if img.height > _LOGO_MAX_HEIGHT:
        ratio = _LOGO_MAX_HEIGHT / img.height
        img = img.resize((max(1, round(img.width * ratio)), _LOGO_MAX_HEIGHT), Image.LANCZOS)

    color_buf = io.BytesIO()
    img.save(color_buf, format="PNG")

    # White variant: only if there's meaningful transparency to carve the silhouette
    alpha = img.getchannel("A")
    has_transparency = alpha.getextrema()[0] < 250
    white_png = None
    if has_transparency:
        w = Image.new("L", img.size, 255)
        white = Image.merge("RGBA", (w, w, w, alpha))
        white_buf = io.BytesIO()
        white.save(white_buf, format="PNG")
        white_png = white_buf.getvalue()

    return color_buf.getvalue(), white_png


def _write_branding_flags(frontend_id: str, uploaded: bool, has_white: bool):
    """Update the server-managed logo flags in branding.json (atomic), keeping mode."""
    path = _branding_path(frontend_id)
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            data = {}
    data["logo_uploaded"] = uploaded
    data["logo_has_white"] = has_white
    data.setdefault("logo_mode", "white")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.rename(path)


@router.post("/{frontend_id}/branding/logo")
async def upload_logo(frontend_id: str, file: UploadFile = File(...), _: dict = Depends(require_admin)):
    """Upload + normalise a logo image (PNG/WEBP/JPG). Stores a colour variant and,
    when the image has transparency, a whitened variant for the blue header."""
    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in _LOGO_ALLOWED:
        raise HTTPException(status_code=400, detail=f"Unsupported format. Allowed: {', '.join(sorted(_LOGO_ALLOWED))}")
    raw = await file.read()
    if len(raw) > _LOGO_MAX_SIZE:
        raise HTTPException(status_code=400, detail="Image too large (max 2 MB)")

    color_png, white_png = _process_logo(raw)

    d = _logo_dir(frontend_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / "logo_color.png").write_bytes(color_png)
    if white_png is not None:
        (d / "logo_white.png").write_bytes(white_png)
    else:
        (d / "logo_white.png").unlink(missing_ok=True)

    _write_branding_flags(frontend_id, uploaded=True, has_white=white_png is not None)
    await _push_logo_to_sidecar(frontend_id)
    return {"logo_uploaded": True, "logo_has_white": white_png is not None}


@router.get("/{frontend_id}/branding/logo/{variant}")
async def get_logo_variant(frontend_id: str, variant: str, _: dict = Depends(require_admin)):
    """Serve a processed logo variant for the admin preview (auth-gated)."""
    from fastapi.responses import FileResponse
    fname = {"color": "logo_color.png", "white": "logo_white.png"}.get(variant)
    if not fname:
        raise HTTPException(status_code=404, detail="Unknown variant")
    p = _logo_dir(frontend_id) / fname
    if not p.exists():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(p, media_type="image/png")


@router.delete("/{frontend_id}/branding/logo")
async def delete_logo(frontend_id: str, _: dict = Depends(require_admin)):
    """Remove the uploaded logo; the frontend falls back to logo_url / bundled default."""
    d = _logo_dir(frontend_id)
    (d / "logo_color.png").unlink(missing_ok=True)
    (d / "logo_white.png").unlink(missing_ok=True)
    _write_branding_flags(frontend_id, uploaded=False, has_white=False)
    await _push_logo_to_sidecar(frontend_id)
    return {"logo_uploaded": False}


async def _push_logo_to_sidecar(frontend_id: str):
    """Push logo image variants + mode to the sidecar (multipart). When no logo is
    uploaded, sends a clear flag so the sidecar drops any stored images."""
    fe = registry.get(frontend_id)
    if not (fe and fe.get("enabled")):
        return

    d = _logo_dir(frontend_id)
    color = d / "logo_color.png"
    white = d / "logo_white.png"

    mode = "white"
    path = _branding_path(frontend_id)
    if path.exists():
        try:
            mode = json.loads(path.read_text()).get("logo_mode", "white")
        except (json.JSONDecodeError, OSError):
            pass

    data = {"mode": mode}
    files = {}
    if color.exists():
        files["color"] = ("logo_color.png", color.read_bytes(), "image/png")
        if white.exists():
            files["white"] = ("logo_white.png", white.read_bytes(), "image/png")
    else:
        data["clear"] = "1"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(f"{fe['url']}/internal/branding-logo", data=data, files=files or None)
            logger.info(f"Logo pushed to {fe['url']} (mode={mode}, clear={'clear' in data})")
    except Exception as e:
        logger.warning(f"Failed to push logo to {fe['url']}: {e}")
