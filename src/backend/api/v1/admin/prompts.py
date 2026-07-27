"""Admin prompts endpoints — list, read, update prompt files.

Sprint 8h: Per-frontend prompt sets with ?frontend_id= query param.
"""

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from src.api.v1.admin.auth import require_admin
from src.services.prompt_assembler import (
    _global_prompts_dir,
    _load,
    get_use_global,
    set_use_global,
    frontend_has_custom_prompts,
    reset_prompt_to_default,
    reset_frontend_prompt_to_factory,
)

logger = logging.getLogger("backend.admin.prompts")

router = APIRouter(prefix="/admin/prompts", tags=["admin-prompts"])

# Category mapping for UI grouping
CATEGORIES: dict[str, list[str]] = {
    "System Prompt": ["core.md", "guardrails.md"],
    "Worker Profiles": ["worker.md", "worker_representative.md"],
    "Organizer Cases": [
        "organizer_document.md", "organizer_interview.md",
        "organizer_advisory.md", "organizer_submit.md",
    ],
    "Officer Cases": [
        "officer_document.md", "officer_interview.md",
        "officer_advisory.md", "officer_submit.md", "officer_training.md",
    ],
    "Context Template": ["context_template.md"],
    "Compression": ["context_compression.md"],
    "Session Summaries": [
        "session_summary_worker.md", "session_summary_representative.md",
        "session_summary_organizer.md", "session_summary_officer.md",
    ],
    "Post-Processing": ["session_summary_uni.md", "internal_case_file.md"],
}


def _resolve_prompts_dir(frontend_id: str | None = None) -> Path:
    """Resolve prompts directory: global or per-frontend."""
    if frontend_id:
        path = Path(f"/app/data/campaigns/{frontend_id}/prompts")
        path.mkdir(parents=True, exist_ok=True)
        return path
    return _global_prompts_dir()


def _file_meta(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "name": path.name,
        "size": stat.st_size,
        "modified": stat.st_mtime,
    }


# --- Global/Custom source flag + reset (Sprint 32) ---

def _all_prompt_names() -> list[str]:
    names: list[str] = []
    for files in CATEGORIES.values():
        names.extend(files)
    return names


class SourceRequest(BaseModel):
    use_global: bool


@router.get("/frontend/{frontend_id}/source")
async def get_source(frontend_id: str, _: dict = Depends(require_admin)):
    """Whether a frontend serves the global prompt set or its own custom copies."""
    return {
        "frontend_id": frontend_id,
        "use_global": get_use_global(frontend_id),
        "has_custom": frontend_has_custom_prompts(frontend_id),
    }


@router.put("/frontend/{frontend_id}/source")
async def set_source(frontend_id: str, req: SourceRequest, _: dict = Depends(require_admin)):
    """Couple a frontend to global, or decouple it to use custom prompts.

    Re-coupling to global auto-deactivates any active feature modules (removing
    their materialised RAG files) — global is pure vanilla and cannot carry
    module content. Custom prompt files are NOT deleted; they simply stop applying.
    """
    deactivated: list[str] = []
    if req.use_global:
        from src.services.modules import get_enabled_modules, set_frontend_override
        from src.services.rag_service import deactivate_module_rag
        for mid in get_enabled_modules(frontend_id):
            deactivate_module_rag(frontend_id, mid)
            deactivated.append(mid)
        set_frontend_override(frontend_id, None)
    set_use_global(frontend_id, req.use_global)
    return {"frontend_id": frontend_id, "use_global": req.use_global, "modules_deactivated": deactivated}


class ResetRequest(BaseModel):
    frontend_id: str | None = None
    to_factory: bool = False
    names: list[str] = []  # empty or ["all"] → every prompt


@router.post("/reset")
async def reset_prompts(req: ResetRequest, _: dict = Depends(require_admin)):
    """Overwrite the selected prompts. Frontend scope: from global (to_factory=False)
    or from factory (True). Global scope (frontend_id=None): always from factory."""
    names = req.names
    if not names or "all" in names:
        names = _all_prompt_names()
    done: list[str] = []
    errors: list[dict] = []
    for name in names:
        try:
            if req.frontend_id and req.to_factory:
                reset_frontend_prompt_to_factory(name, req.frontend_id)
            else:
                # frontend + !to_factory → from global; global scope → from factory
                reset_prompt_to_default(name, req.frontend_id)
            done.append(name)
        except (FileNotFoundError, ValueError) as e:
            errors.append({"name": name, "error": str(e)})
    return {"reset": done, "errors": errors}


# --- Standard prompt CRUD with optional frontend_id ---

@router.get("")
async def list_prompts(frontend_id: str | None = Query(None), _: dict = Depends(require_admin)):
    """List all prompt files grouped by category."""
    prompts_dir = _resolve_prompts_dir(frontend_id)
    result: dict[str, list[dict[str, Any]]] = {}

    for category, files in CATEGORIES.items():
        items = []
        for fname in files:
            path = prompts_dir / fname
            if path.exists():
                items.append(_file_meta(path))
            else:
                items.append({"name": fname, "size": 0, "modified": None})
        result[category] = items

    return {"categories": result}


@router.get("/{name}/preview")
async def preview_prompt(name: str, frontend_id: str | None = Query(None), _: dict = Depends(require_admin)):
    """Assembled view: the prompt with its {{module_*}} slots resolved for this
    scope — a frontend's active modules fill them; global scope resolves to empty
    slots. Read-only; mirrors exactly what the LLM receives at assembly time."""
    return {"name": name, "content": _load(name, frontend_id)}


@router.get("/{name}")
async def read_prompt(name: str, frontend_id: str | None = Query(None), _: dict = Depends(require_admin)):
    """Read a prompt's content. Frontend scope shows the custom copy if present,
    otherwise the global file (the effective content, shown read-only when coupled)."""
    if frontend_id:
        cand = _resolve_prompts_dir(frontend_id) / name
        if cand.exists():
            return {"name": name, "content": cand.read_text(), "custom": True}
    gpath = _global_prompts_dir() / name
    if gpath.exists():
        return {"name": name, "content": gpath.read_text(), "custom": False}
    raise HTTPException(status_code=404, detail=f"Prompt not found: {name}")


class SavePromptRequest(BaseModel):
    content: str


@router.put("/{name}")
async def save_prompt(name: str, req: SavePromptRequest, frontend_id: str | None = Query(None), _: dict = Depends(require_admin)):
    """Save prompt file content (atomic write)."""
    prompts_dir = _resolve_prompts_dir(frontend_id)
    path = prompts_dir / name
    # Atomic write
    tmp = path.with_suffix(".tmp")
    tmp.write_text(req.content)
    tmp.rename(path)
    logger.info(f"Prompt saved: {name} (frontend={frontend_id or 'global'})")
    return {"name": name, "size": path.stat().st_size, "modified": path.stat().st_mtime}
