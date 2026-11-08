"""Send a frontend its resolved branding (Sprint 43): tokens, texts, translations, logos.

One builder for every caller (admin saves, the polling loop after a sidecar restart
or a global change), so a frontend always gets the same thing.
"""

import json
import logging
from typing import Any

import httpx

from src.core.paths import campaign_dir
from src.services import branding_tokens as bt

logger = logging.getLogger("backend.branding_push")

_ROLES = ("worker", "representative", "organizer", "officer")


def has_custom_text(data: dict[str, Any]) -> bool:
    return bool(
        data.get("disclaimer_text")
        or data.get("instructions_text")
        or any(data.get(f"instructions_text_{r}") for r in _ROLES)
    )


def _saved(frontend_id: str) -> dict[str, Any]:
    try:
        data = json.loads((campaign_dir(frontend_id) / "branding.json").read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def build_payload(frontend_id: str) -> dict[str, Any]:
    from src.services.branding_translator import load_translations

    data = _saved(frontend_id)
    vals = bt.values(frontend_id)
    custom = has_custom_text(data)
    return {
        **data,
        "app_title": vals["tool_name"],      # the legacy field now follows the tool_name token
        "custom": custom,
        "translations": load_translations(frontend_id),
        "tokens": vals,
        "logos": bt.logo_status(frontend_id),
    }


async def push_logos(client: httpx.AsyncClient, url: str, frontend_id: str) -> None:
    """Push the logo of every slot. Order matters for sidecars from before Sprint 43, which
    keep one logo and ignore `slot`: the top-bar logo goes last so that is the one they keep."""
    mode = _saved(frontend_id).get("logo_mode", "white")
    for slot in ("chat_bg", "page", "header"):
        eff = bt.effective_logo(frontend_id, slot)
        data = {"slot": slot, "mode": mode}
        files = {}
        if eff["color"]:
            files["color"] = (f"logo_{slot}_color.png", eff["color"].read_bytes(), "image/png")
            if eff["white"]:
                files["white"] = (f"logo_{slot}_white.png", eff["white"].read_bytes(), "image/png")
        else:
            data["clear"] = "1"
        await client.post(f"{url}/internal/branding-logo", data=data, files=files or None)
