from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI(title="HRDD Helper Backend", version="2.0.0")


@app.get("/health")
async def health():
    return JSONResponse({"status": "ok"})
