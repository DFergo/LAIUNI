# Copyright (c) 2026 UNI Global Union. All rights reserved. See LICENSE.

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from src.api.v1.admin.auth import router as auth_router
from src.api.v1.admin.frontends import router as frontends_router
from src.api.v1.admin.llm import router as llm_router, fe_router as llm_fe_router
from src.api.v1.admin.prompts import router as prompts_router
from src.api.v1.admin.sessions import router as sessions_router
from src.api.v1.admin.rag import router as rag_router
from src.api.v1.admin.smtp import router as smtp_router
from src.api.v1.admin.knowledge import router as knowledge_router
from src.api.v1.admin.knowledge import ensure_defaults as ensure_knowledge_defaults
from src.core.config import config
from src.services.polling import polling_loop
from src.services.session_lifecycle import lifecycle_loop
from src.services.prompt_assembler import ensure_defaults

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("backend")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Install default prompt files and knowledge base if missing
    ensure_defaults()
    ensure_knowledge_defaults()
    # Initialize RAG index (loads from disk or builds from documents)
    from src.services.rag_service import initialize as init_rag
    init_rag()
    # Non-blocking SMTP health check (logs warning if unreachable)
    from src.services.smtp_service import check_smtp_health
    asyncio.create_task(check_smtp_health())
    # Start polling loop on startup
    poll_task = asyncio.create_task(polling_loop(config.poll_interval_seconds))
    lifecycle_task = asyncio.create_task(lifecycle_loop())
    logger.info("Backend started, polling loop + lifecycle scanner running")
    yield
    poll_task.cancel()
    lifecycle_task.cancel()
    for t in [poll_task, lifecycle_task]:
        try:
            await t
        except asyncio.CancelledError:
            pass


app = FastAPI(title="HRDD Helper Backend", version="2.0.0", lifespan=lifespan)

# Register API routes
app.include_router(auth_router)
app.include_router(frontends_router)
app.include_router(llm_router)
app.include_router(llm_fe_router)
app.include_router(prompts_router)
app.include_router(sessions_router)
app.include_router(rag_router)
app.include_router(smtp_router)
app.include_router(knowledge_router)

# Admin SPA static files
ADMIN_DIST = Path("/app/admin/dist")


@app.get("/health")
async def health():
    return JSONResponse({"status": "ok"})


# Serve admin SPA — must be after API routes
if ADMIN_DIST.exists():
    app.mount("/assets", StaticFiles(directory=ADMIN_DIST / "assets"), name="admin-assets")

    @app.get("/{full_path:path}")
    async def serve_admin_spa(full_path: str):
        """Serve admin SPA for all non-API routes."""
        file_path = ADMIN_DIST / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(ADMIN_DIST / "index.html")
