from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from src.api.v1.admin.auth import router as auth_router

app = FastAPI(title="HRDD Helper Backend", version="2.0.0")

# Register API routes
app.include_router(auth_router)

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
