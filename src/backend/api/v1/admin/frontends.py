import httpx
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from src.api.v1.admin.auth import require_admin
from src.services.frontend_registry import registry
from src.services.prompt_assembler import get_prompt_mode, copy_global_to_frontend

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
