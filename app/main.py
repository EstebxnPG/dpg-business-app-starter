from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.database import database_ready

app = FastAPI(title="DPG Business App Starter", version="0.1.0")


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready", tags=["system"])
def ready() -> JSONResponse:
    if not database_ready():
        return JSONResponse(status_code=503, content={"status": "unavailable"})
    return JSONResponse(content={"status": "ok"})
