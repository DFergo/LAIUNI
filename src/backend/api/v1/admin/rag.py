"""Admin RAG endpoints — upload, list, delete documents.

Sprint 8h: Per-frontend campaign documents with ?frontend_id= query param.
"""

import logging
import shutil
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query

from src.api.v1.admin.auth import require_admin
from src.core.config import config

logger = logging.getLogger("backend.admin.rag")

router = APIRouter(prefix="/admin/rag", tags=["admin-rag"])

ALLOWED_EXTENSIONS = {".md", ".txt", ".json"}
MAX_FILE_SIZE = config.file_max_size_mb * 1024 * 1024


def _docs_dir(frontend_id: str | None = None) -> Path:
    if frontend_id:
        path = Path(f"/app/data/campaigns/{frontend_id}/documents")
    else:
        path = Path("/app/data/documents")
    path.mkdir(parents=True, exist_ok=True)
    return path


def _file_meta(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "name": path.name,
        "size": stat.st_size,
        "modified": stat.st_mtime,
    }


@router.get("/documents")
async def list_documents(frontend_id: str | None = Query(None), _: dict = Depends(require_admin)):
    """List RAG documents (global or per-frontend)."""
    docs_dir = _docs_dir(frontend_id)
    docs = []
    for f in sorted(docs_dir.iterdir()):
        if f.is_file() and f.suffix in ALLOWED_EXTENSIONS:
            docs.append(_file_meta(f))
    return {"documents": docs}


@router.post("/upload")
async def upload_document(file: UploadFile = File(...), frontend_id: str | None = Query(None), _: dict = Depends(require_admin)):
    """Upload a document for RAG indexing (global or per-frontend)."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"File type not allowed: {ext}. Use: {', '.join(ALLOWED_EXTENSIONS)}")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail=f"File too large. Max: {config.file_max_size_mb}MB")

    dest = _docs_dir(frontend_id) / file.filename
    dest.write_bytes(content)
    logger.info(f"Document uploaded: {file.filename} ({len(content)} bytes) [frontend={frontend_id or 'global'}]")
    return {"name": file.filename, "size": len(content)}


@router.delete("/documents/{name}")
async def delete_document(name: str, frontend_id: str | None = Query(None), _: dict = Depends(require_admin)):
    """Delete a RAG document (global or per-frontend)."""
    path = _docs_dir(frontend_id) / name
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Document not found: {name}")
    path.unlink()
    logger.info(f"Document deleted: {name} [frontend={frontend_id or 'global'}]")
    return {"status": "deleted", "name": name}


@router.post("/reindex")
async def reindex_documents(frontend_id: str | None = Query(None), _: dict = Depends(require_admin)):
    """Rebuild RAG index (global or per-frontend)."""
    if frontend_id:
        from src.services.rag_service import reindex_campaign
        result = reindex_campaign(frontend_id)
        logger.info(f"Campaign reindex completed for {frontend_id}: {result}")
    else:
        from src.services.rag_service import reindex as rag_reindex
        result = rag_reindex()
        logger.info(f"Global reindex completed: {result}")
    return result


# --- Campaign RAG config (Sprint 8h) ---

@router.get("/campaign/{frontend_id}/config")
async def get_campaign_config(frontend_id: str, _: dict = Depends(require_admin)):
    """Get campaign RAG config for a frontend."""
    from src.services.rag_service import get_campaign_rag_config
    return get_campaign_rag_config(frontend_id)


@router.put("/campaign/{frontend_id}/config")
async def update_campaign_config(frontend_id: str, req: dict, _: dict = Depends(require_admin)):
    """Update campaign RAG config for a frontend."""
    from src.services.rag_service import set_campaign_rag_config
    include_global = req.get("include_global_rag", True)
    result = set_campaign_rag_config(frontend_id, include_global)
    return result


@router.get("/stats")
async def index_stats(_: dict = Depends(require_admin)):
    """Get RAG index statistics."""
    from src.services.rag_service import get_index_stats
    return get_index_stats()
