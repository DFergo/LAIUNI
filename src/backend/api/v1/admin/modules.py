"""Admin endpoints for feature modules.

Sprint 32: modules are per-frontend only and can be toggled only when the
frontend is decoupled from the global prompt set. Activating a module copies its
RAG source files into the frontend's documents (materialised + locked); disabling
it removes them. There is no global module set.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.api.v1.admin.auth import require_admin
from src.services import modules as mod
from src.services.prompt_assembler import get_use_global
from src.services.rag_service import activate_module_rag, deactivate_module_rag

logger = logging.getLogger("backend.admin.modules")

router = APIRouter(prefix="/admin/modules", tags=["admin-modules"])


class FrontendModules(BaseModel):
    enabled: list[str]


@router.get("")
async def list_modules(_: dict = Depends(require_admin)):
    """All modules bundled with the app, with the number of RAG files each adds."""
    available = [
        {**m, "doc_count": len(mod.module_document_names(m["id"]))}
        for m in mod.list_available_modules()
    ]
    return {"available": available}


@router.get("/frontend/{frontend_id}")
async def get_frontend(frontend_id: str, _: dict = Depends(require_admin)):
    return {
        "frontend_id": frontend_id,
        "enabled": mod.get_enabled_modules(frontend_id),
        "use_global": get_use_global(frontend_id),
    }


@router.put("/frontend/{frontend_id}")
async def set_frontend(frontend_id: str, req: FrontendModules, _: dict = Depends(require_admin)):
    """Set the enabled module set for a frontend. Diffs against the current set:
    newly-enabled modules materialise their RAG files, disabled ones remove theirs."""
    if get_use_global(frontend_id):
        raise HTTPException(
            status_code=409,
            detail="Decouple this frontend from the global prompt set before enabling modules.",
        )
    current = set(mod.get_enabled_modules(frontend_id))
    target = set(mod._valid_ids(req.enabled))

    added_files: dict[str, list[str]] = {}
    for mid in target - current:
        added_files[mid] = activate_module_rag(frontend_id, mid).get("added", [])
    for mid in current - target:
        deactivate_module_rag(frontend_id, mid)

    mod.set_frontend_override(frontend_id, sorted(target))
    return {"frontend_id": frontend_id, "enabled": sorted(target), "added_files": added_files}
