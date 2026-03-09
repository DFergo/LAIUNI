from fastapi import FastAPI

app = FastAPI(title="HRDD Frontend Sidecar", version="2.0.0")


@app.get("/internal/health")
async def health():
    return {"status": "ok"}
