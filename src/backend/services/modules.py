"""Feature modules — optional bundles that add framework knowledge to a vanilla,
industry-agnostic install, toggled globally or per-frontend (Sprint 29).

A module lives in src/backend/modules/{id}/:
  meta.json          {"id": "...", "name": "..."}
  framework.md       fragment injected into the {{module_frameworks}} slot
  report_section.md  fragment injected into the {{module_report_sections}} slot
  intake.md          fragment injected into the {{module_intake}} slot (institutional
                     intake prompts — drives module-specific questions like certification)
  rag/               RAG source docs (indexed per-module when the module is active)

Enabled set: global config/modules.json {"enabled": [...]} plus an optional
per-frontend override at campaigns/{fid}/modules.json {"override": bool,
"enabled": [...]}. Default: none (vanilla). Prompts reference module content
through {{module_<slot>}} tokens, so the model sees one coherent list with no
"this deployment also…" seam.
"""

import json
import logging
from pathlib import Path

from src.core.paths import CAMPAIGNS_DIR

logger = logging.getLogger("backend.modules")

# Modules shipped with the app (read-only, in the image).
_MODULES_DIR = Path(__file__).parent.parent / "modules"

_DOC_SUFFIXES = {".md", ".txt", ".json", ".pdf"}

# Prompt slot name -> the module fragment filename that fills it.
_SLOT_FILES = {
    "frameworks": "framework.md",
    "report_sections": "report_section.md",
    "intake": "intake.md",
}


def modules_dir() -> Path:
    return _MODULES_DIR


def module_documents_dir(module_id: str) -> Path:
    return _MODULES_DIR / module_id / "rag"


def list_available_modules() -> list[dict]:
    """All modules bundled with the app: [{id, name}]."""
    out: list[dict] = []
    if _MODULES_DIR.is_dir():
        for d in sorted(_MODULES_DIR.iterdir()):
            meta_path = d / "meta.json"
            if d.is_dir() and meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text())
                    out.append({"id": meta.get("id", d.name), "name": meta.get("name", d.name)})
                except Exception as e:
                    logger.warning(f"Bad module meta for {d.name}: {e}")
    return out


def _valid_ids(ids: list[str]) -> list[str]:
    available = {m["id"] for m in list_available_modules()}
    return [i for i in ids if i in available]


def module_document_names(module_id: str) -> list[str]:
    """Names of the RAG source files a module contributes (for the activation
    preview: "N files will be added to this frontend's RAG")."""
    d = module_documents_dir(module_id)
    if not d.is_dir():
        return []
    return sorted(f.name for f in d.iterdir() if f.is_file() and f.suffix.lower() in _DOC_SUFFIXES)


# --- Per-frontend enabled set (Sprint 32: modules are per-frontend only) ---

def _frontend_config_path(frontend_id: str) -> Path:
    return CAMPAIGNS_DIR / frontend_id / "modules.json"


def get_frontend_override(frontend_id: str) -> list[str] | None:
    """The frontend's override list, or None when it inherits the global set."""
    p = _frontend_config_path(frontend_id)
    if p.exists():
        try:
            data = json.loads(p.read_text())
            if data.get("override"):
                return list(data.get("enabled", []))
        except Exception as e:
            logger.warning(f"Failed to read modules override for {frontend_id}: {e}")
    return None


def set_frontend_override(frontend_id: str, enabled: list[str] | None) -> None:
    """Set a per-frontend override, or pass None to clear it (inherit global)."""
    p = _frontend_config_path(frontend_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    if enabled is None:
        p.write_text(json.dumps({"override": False, "enabled": []}))
    else:
        p.write_text(json.dumps({"override": True, "enabled": _valid_ids(enabled)}))
    logger.info(f"Modules override for {frontend_id}: {enabled}")


def get_enabled_modules(frontend_id: str | None = None) -> list[str]:
    """Effective enabled module ids for a frontend. Modules are per-frontend only
    (Sprint 32) and are toggled from the Prompts panel when the frontend is
    decoupled from global; there is no global module set."""
    if not frontend_id:
        return []
    override = get_frontend_override(frontend_id)
    return override if override is not None else []


# --- Slot rendering ---

def _load_fragment(module_id: str, slot: str) -> str:
    fname = _SLOT_FILES.get(slot)
    if not fname:
        return ""
    path = _MODULES_DIR / module_id / fname
    if path.exists():
        return path.read_text().strip()
    return ""


def render_slot(slot: str, frontend_id: str | None = None) -> str:
    """Concatenate the `slot` fragment from every enabled module."""
    frags = [_load_fragment(mid, slot) for mid in get_enabled_modules(frontend_id)]
    return "\n\n".join(f for f in frags if f)


def apply_slots(text: str, frontend_id: str | None = None) -> str:
    """Replace {{module_<slot>}} tokens with the active modules' fragments.

    No-op (returns text unchanged) when no module tokens are present.
    """
    if "{{module_" not in text:
        return text
    for slot in _SLOT_FILES:
        token = "{{module_" + slot + "}}"
        if token in text:
            text = text.replace(token, render_slot(slot, frontend_id))
    return text
