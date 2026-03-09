import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from src.api.v1.admin.auth import router as auth_router
from src.api.v1.admin.frontends import router as frontends_router
from src.core.config import config
from src.services.polling import polling_loop

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("backend")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start polling loop on startup
    task = asyncio.create_task(polling_loop(config.poll_interval_seconds))
    logger.info("Backend started, polling loop running")
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="HRDD Helper Backend", version="2.0.0", lifespan=lifespan)

# Register API routes
app.include_router(auth_router)
app.include_router(frontends_router)

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
