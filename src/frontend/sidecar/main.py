import json
import os

from fastapi import FastAPI

app = FastAPI(title="HRDD Frontend Sidecar", version="2.0.0")

# Load deployment config
_config_path = os.environ.get("DEPLOYMENT_JSON_PATH", "/app/config/deployment_frontend_worker.json")
_config = {}
if os.path.exists(_config_path):
    with open(_config_path) as f:
        _config = json.load(f)


@app.get("/internal/health")
async def health():
    return {"status": "ok"}


@app.get("/internal/config")
async def get_config():
    """Return deployment config for React app and backend discovery."""
    return {
        "role": "frontend",
        "frontend_type": _config.get("frontend_type", "worker"),
        "session_resume_window_hours": _config.get("session_resume_window_hours", 48),
        "disclaimer_enabled": _config.get("disclaimer_enabled", True),
        "auth_required": _config.get("auth_required", False),
    }
