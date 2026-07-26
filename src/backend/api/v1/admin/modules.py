"""Admin endpoints for feature modules (Sprint 29).

List available modules, set the global enabled set, and set/clear a per-frontend
override.
"""

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.api.v1.admin.auth import require_admin
from src.services import modules as mod

logger = logging.getLogger("backend.admin.modules")

router = APIRouter(prefix="/admin/modules", tags=["admin-modules"])


class GlobalModules(BaseModel):
    enabled: list[str]


class FrontendModules(BaseModel):
    override: bool
    enabled: list[str] = []


@router.get("")
async def list_modules(_: dict = Depends(require_admin)):
    return {
        "available": mod.list_available_modules(),
        "global_enabled": mod.get_global_enabled(),
    }


@router.put("/global")
async def set_global(req: GlobalModules, _: dict = Depends(require_admin)):
    return {"enabled": mod.set_global_enabled(req.enabled)}


@router.get("/frontend/{frontend_id}")
async def get_frontend(frontend_id: str, _: dict = Depends(require_admin)):
    override = mod.get_frontend_override(frontend_id)
    return {
        "frontend_id": frontend_id,
        "override": override is not None,
        "enabled": override if override is not None else mod.get_global_enabled(),
        "effective": mod.get_enabled_modules(frontend_id),
    }


@router.put("/frontend/{frontend_id}")
async def set_frontend(frontend_id: str, req: FrontendModules, _: dict = Depends(require_admin)):
    mod.set_frontend_override(frontend_id, req.enabled if req.override else None)
    return {"frontend_id": frontend_id, "override": req.override, "effective": mod.get_enabled_modules(frontend_id)}
