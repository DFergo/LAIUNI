"""Admin RAG endpoints — upload, list, delete documents."""

import logging
import shutil
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File

from src.api.v1.admin.auth import require_admin
from src.core.config import config

logger = logging.getLogger("backend.admin.rag")

router = APIRouter(prefix="/admin/rag", tags=["admin-rag"])

ALLOWED_EXTENSIONS = {".md", ".txt", ".json"}
MAX_FILE_SIZE = config.file_max_size_mb * 1024 * 1024


def _docs_dir() -> Path:
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
async def list_documents(_: dict = Depends(require_admin)):
    """List all RAG documents."""
    docs_dir = _docs_dir()
    docs = []
    for f in sorted(docs_dir.iterdir()):
        if f.is_file() and f.suffix in ALLOWED_EXTENSIONS:
            docs.append(_file_meta(f))
    return {"documents": docs}


@router.post("/upload")
async def upload_document(file: UploadFile = File(...), _: dict = Depends(require_admin)):
    """Upload a document for RAG indexing."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"File type not allowed: {ext}. Use: {', '.join(ALLOWED_EXTENSIONS)}")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail=f"File too large. Max: {config.file_max_size_mb}MB")

    dest = _docs_dir() / file.filename
    dest.write_bytes(content)
    logger.info(f"Document uploaded: {file.filename} ({len(content)} bytes)")
    return {"name": file.filename, "size": len(content)}


@router.delete("/documents/{name}")
async def delete_document(name: str, _: dict = Depends(require_admin)):
    """Delete a RAG document."""
    path = _docs_dir() / name
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Document not found: {name}")
    path.unlink()
    logger.info(f"Document deleted: {name}")
    return {"status": "deleted", "name": name}


@router.post("/reindex")
async def reindex(_: dict = Depends(require_admin)):
    """Trigger RAG reindex (stub — actual indexing in Sprint 7)."""
    docs_dir = _docs_dir()
    count = sum(1 for f in docs_dir.iterdir() if f.is_file() and f.suffix in ALLOWED_EXTENSIONS)
    logger.info(f"Reindex requested ({count} documents)")
    return {"status": "reindex_requested", "document_count": count}
