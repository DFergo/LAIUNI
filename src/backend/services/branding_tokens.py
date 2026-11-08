"""Branding tokens (Sprint 43, docs/BRANDING-TOKENS.md).

One catalog of the values that make the app look like an organization: its name,
the tool's name, the colours and the logos. Nothing in the app hardcodes them;
every place that shows one reads the token.

Two levels: the global catalog (`config/branding_tokens.json`, applies to every
frontend) and per-frontend overrides (`campaigns/{id}/branding.json` → "tokens").
An unset token inherits the global value, which inherits the default below.

Standard library only (Pillow is imported lazily by the callers that process logos).
"""

import json
import logging
import re
from pathlib import Path
from typing import Any

from src.core.paths import CONFIG_DIR, campaign_dir

logger = logging.getLogger("backend.branding_tokens")

# The one place where the defaults live (the values UNI has always used).
# The frontend keeps a copy for the moments before the backend has pushed
# anything; tests/test_branding_tokens.py fails if the two drift apart.
TEXT_MAX = {"org_name": 120, "org_short_name": 40, "tool_name": 60}

CATALOG: list[dict[str, Any]] = [
    {"name": "org_name", "kind": "text", "default": "UNI Global Union",
     "label": "Organization name", "used_in": "Top bar (right), logo descriptions, default disclaimer and instructions, emails"},
    {"name": "org_short_name", "kind": "text", "default": "UNI",
     "label": "Organization short name", "used_in": "Short mentions in default texts"},
    {"name": "tool_name", "kind": "text", "default": "HRDD Helper",
     "label": "Tool name", "used_in": "Top bar title, browser tab, emails"},
    {"name": "color_primary", "kind": "color", "default": "#003087",
     "label": "Primary colour", "used_in": "Top bar, buttons, links, user chat bubbles, focus rings"},
    {"name": "color_on_primary", "kind": "color", "default": "#FFFFFF",
     "label": "Text on the primary colour", "used_in": "Text and icons on the top bar, buttons and user bubbles"},
    {"name": "color_accent", "kind": "color", "default": "#E31837",
     "label": "Accent colour", "used_in": "Alerts, errors, destructive actions"},
    {"name": "color_dark", "kind": "color", "default": "#1A1A2E",
     "label": "Dark colour", "used_in": "Admin panel header"},
]
LOGO_SLOTS = {
    "header": "Top bar (the white version is used on the primary colour)",
    "page": "Language, disclaimer and instructions pages",
    "chat_bg": "Faded background of the chat",
}
# Shown in the catalog, never editable.
FIXED = {"copyright_holder": "UNI Global Union"}

DEFAULTS: dict[str, str] = {t["name"]: t["default"] for t in CATALOG}
_KINDS = {t["name"]: t["kind"] for t in CATALOG}
_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")

GLOBAL_FILE = CONFIG_DIR / "branding_tokens.json"
GLOBAL_LOGO_DIR = CONFIG_DIR / "branding"


class TokenError(ValueError):
    pass


# --------------------------------------------------------------------------- validation

def validate(values: dict[str, Any]) -> dict[str, str]:
    """Check a {token: value} dict; return it normalised. An empty value means
    "unset" and is dropped (the token inherits)."""
    out: dict[str, str] = {}
    for name, raw in (values or {}).items():
        if name in FIXED:
            raise TokenError(f"'{name}' is fixed (the copyright holder) and cannot be changed.")
        if name not in _KINDS:
            raise TokenError(f"Unknown token '{name}'. Tokens: {', '.join(DEFAULTS)}.")
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            continue
        if not isinstance(raw, str):
            raise TokenError(f"'{name}' must be text.")
        value = raw.strip()
        if _KINDS[name] == "color":
            if not _COLOR.match(value):
                raise TokenError(f"'{name}' must be a colour like #003087.")
            value = value.upper()
        else:
            if len(value) > TEXT_MAX[name]:
                raise TokenError(f"'{name}' is longer than {TEXT_MAX[name]} characters.")
            if _CONTROL.search(value) or "{{" in value or "}}" in value:
                raise TokenError(f"'{name}' cannot contain line breaks or {{{{ }}}}.")
        out[name] = value
    return out


# --------------------------------------------------------------------------- storage

def _read(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _atomic_write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    tmp.rename(path)


def global_overrides() -> dict[str, str]:
    return {k: v for k, v in _read(GLOBAL_FILE).get("values", {}).items() if k in _KINDS}


def save_global(overrides: dict[str, str]) -> None:
    _atomic_write(GLOBAL_FILE, {"values": overrides})


def _frontend_branding_path(frontend_id: str) -> Path:
    return campaign_dir(frontend_id) / "branding.json"


def frontend_overrides(frontend_id: str) -> dict[str, str]:
    data = _read(_frontend_branding_path(frontend_id))
    own = {k: v for k, v in (data.get("tokens") or {}).items() if k in _KINDS}
    # app_title predates tokens: it is the frontend's own tool name.
    if data.get("app_title") and "tool_name" not in own:
        own["tool_name"] = data["app_title"]
    return own


def save_frontend_overrides(frontend_id: str, overrides: dict[str, str]) -> None:
    """Store the frontend's own tokens inside its branding.json (other fields kept)."""
    path = _frontend_branding_path(frontend_id)
    data = _read(path)
    data["tokens"] = overrides
    _atomic_write(path, data)


# --------------------------------------------------------------------------- resolution

def resolve(frontend_id: str | None = None) -> dict[str, dict[str, str]]:
    """Every token with its effective value and where it comes from."""
    glob = global_overrides()
    own = frontend_overrides(frontend_id) if frontend_id else {}
    out = {}
    for name, default in DEFAULTS.items():
        if name in own:
            out[name] = {"value": own[name], "source": "frontend"}
        elif name in glob:
            out[name] = {"value": glob[name], "source": "global"}
        else:
            out[name] = {"value": default, "source": "default"}
    return out


def values(frontend_id: str | None = None) -> dict[str, str]:
    return {k: v["value"] for k, v in resolve(frontend_id).items()}


def render(text: str, vals: dict[str, str] | None = None) -> str:
    """Replace {{token}} in a text (unknown names are left alone)."""
    vals = vals or values()
    return re.sub(r"\{\{\s*([a-z_]+)\s*\}\}", lambda m: vals.get(m.group(1), m.group(0)), text or "")


def tool_name(frontend_id: str = "") -> str:
    return values(frontend_id or None)["tool_name"]


def org_name(frontend_id: str = "") -> str:
    return values(frontend_id or None)["org_name"]


# --------------------------------------------------------------------------- contrast

def _luminance(hex_color: str) -> float:
    chans = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in chans]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast_ratio(a: str, b: str) -> float:
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def contrast_warnings(vals: dict[str, str]) -> list[str]:
    """Readability checks (WCAG): shown in the admin, never blocking."""
    checks = [
        ("color_on_primary", "color_primary", 4.5, "Text on the primary colour is hard to read"),
        ("color_accent", "#FFFFFF", 3.0, "The accent colour is hard to read as text on white"),
        ("color_dark", "#FFFFFF", 4.5, "White text on the dark colour is hard to read"),
    ]
    out = []
    for fg, bg, minimum, msg in checks:
        ratio = contrast_ratio(vals[fg], vals.get(bg, bg))
        if ratio < minimum:
            out.append(f"{msg} (contrast {ratio:.1f}:1, at least {minimum:g}:1 recommended).")
    return out


# --------------------------------------------------------------------------- logos

def _slot_dir(frontend_id: str | None) -> Path:
    return campaign_dir(frontend_id) if frontend_id else GLOBAL_LOGO_DIR


def logo_path(frontend_id: str | None, slot: str, variant: str) -> Path:
    return _slot_dir(frontend_id) / f"logo_{slot}_{variant}.png"


def _legacy_path(frontend_id: str, variant: str) -> Path:
    """Before Sprint 43 a frontend had one logo (logo_color.png / logo_white.png) used on the top bar and the pages."""
    return campaign_dir(frontend_id) / f"logo_{variant}.png"


def own_logo(frontend_id: str | None, slot: str) -> dict[str, Path | None]:
    """The logo uploaded at exactly this level (no inheritance)."""
    color, white = logo_path(frontend_id, slot, "color"), logo_path(frontend_id, slot, "white")
    if frontend_id and slot in ("header", "page") and not color.exists():
        color, white = _legacy_path(frontend_id, "color"), _legacy_path(frontend_id, "white")
    return {"color": color if color.exists() else None, "white": white if white.exists() and color.exists() else None}


def effective_logo(frontend_id: str | None, slot: str) -> dict[str, Any]:
    """Logo the frontend should show: its own upload, else (unless it uses a logo URL for the
    header / pages) the global upload, else none (the app's bundled default)."""
    if frontend_id:
        own = own_logo(frontend_id, slot)
        if own["color"]:
            return {"source": "frontend", **own}
        has_url = bool(_read(_frontend_branding_path(frontend_id)).get("logo_url")) and slot in ("header", "page")
        if has_url:
            return {"source": "none", "color": None, "white": None}
    glob = own_logo(None, slot)
    if glob["color"]:
        return {"source": "global", **glob}
    return {"source": "none", "color": None, "white": None}


def logo_status(frontend_id: str | None = None) -> dict[str, dict[str, Any]]:
    out = {}
    for slot, desc in LOGO_SLOTS.items():
        eff = effective_logo(frontend_id, slot)
        out[slot] = {"description": desc, "source": eff["source"], "uploaded": eff["color"] is not None,
                     "has_white": eff["white"] is not None}
    return out


def save_logo(frontend_id: str | None, slot: str, color_png: bytes, white_png: bytes | None) -> None:
    if slot not in LOGO_SLOTS:
        raise TokenError(f"Unknown logo slot '{slot}'. Slots: {', '.join(LOGO_SLOTS)}.")
    color, white = logo_path(frontend_id, slot, "color"), logo_path(frontend_id, slot, "white")
    color.parent.mkdir(parents=True, exist_ok=True)
    color.write_bytes(color_png)
    if white_png is not None:
        white.write_bytes(white_png)
    else:
        white.unlink(missing_ok=True)


def delete_logo(frontend_id: str | None, slot: str) -> None:
    if slot not in LOGO_SLOTS:
        raise TokenError(f"Unknown logo slot '{slot}'. Slots: {', '.join(LOGO_SLOTS)}.")
    for variant in ("color", "white"):
        logo_path(frontend_id, slot, variant).unlink(missing_ok=True)
        if frontend_id and slot in ("header", "page"):
            _legacy_path(frontend_id, variant).unlink(missing_ok=True)


# --------------------------------------------------------------------------- catalog for the admin / MCP

def catalog(frontend_id: str | None = None) -> dict[str, Any]:
    """Everything the admin panel and the MCP need: tokens (value, default, source), logos, warnings."""
    res = resolve(frontend_id)
    # What a token becomes when this level sets nothing: the global value (or the default).
    inherited = resolve(None) if frontend_id else {k: {"value": v} for k, v in DEFAULTS.items()}
    tokens = [{**{k: t[k] for k in ("name", "kind", "label", "used_in", "default")}, **res[t["name"]],
               "inherited": inherited[t["name"]]["value"]} for t in CATALOG]
    vals = {k: v["value"] for k, v in res.items()}
    return {"tokens": tokens, "logos": logo_status(frontend_id),
            "fixed": [{"name": k, "value": v, "note": "Copyright line; cannot be changed."} for k, v in FIXED.items()],
            "warnings": contrast_warnings(vals)}
