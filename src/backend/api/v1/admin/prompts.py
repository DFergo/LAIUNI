"""Admin prompts endpoints — list, read, update prompt files."""

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.api.v1.admin.auth import require_admin
from src.services.prompt_assembler import _prompts_dir

logger = logging.getLogger("backend.admin.prompts")

router = APIRouter(prefix="/admin/prompts", tags=["admin-prompts"])

# Category mapping for UI grouping
CATEGORIES: dict[str, list[str]] = {
    "System Prompt": ["core.md"],
    "User Prompts": ["worker.md", "worker_representative.md", "organizer.md", "officer.md"],
    "Use Cases": ["documentation.md", "advisory.md", "training.md"],
    "Context Template": ["context_template.md"],
    "Post-Processing": ["session_summary.md", "internal_case_file.md"],
}


def _file_meta(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "name": path.name,
        "size": stat.st_size,
        "modified": stat.st_mtime,
    }


@router.get("")
async def list_prompts(_: dict = Depends(require_admin)):
    """List all prompt files grouped by category."""
    prompts_dir = _prompts_dir()
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


@router.get("/{name}")
async def read_prompt(name: str, _: dict = Depends(require_admin)):
    """Read a prompt file's content."""
    path = _prompts_dir() / name
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Prompt not found: {name}")
    return {"name": name, "content": path.read_text()}


class SavePromptRequest(BaseModel):
    content: str


@router.put("/{name}")
async def save_prompt(name: str, req: SavePromptRequest, _: dict = Depends(require_admin)):
    """Save prompt file content (atomic write)."""
    path = _prompts_dir() / name
    # Atomic write
    tmp = path.with_suffix(".tmp")
    tmp.write_text(req.content)
    tmp.rename(path)
    logger.info(f"Prompt saved: {name}")
    return {"name": name, "size": path.stat().st_size, "modified": path.stat().st_mtime}
