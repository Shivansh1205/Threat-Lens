"""FastAPI application entrypoint.

Phase 2 (skeleton pipeline): a health check plus the ingestion and alerts
routers, mounted under ``/api/v1``. Detection is a stub; real rules land in
Phase 3.
"""

from fastapi import FastAPI

from app.api import alerts, logs
from app.config import get_settings

settings = get_settings()

app = FastAPI(title=settings.APP_NAME)

app.include_router(logs.router, prefix="/api/v1")
app.include_router(alerts.router, prefix="/api/v1")


@app.get("/health")
def health_check() -> dict[str, str]:
    """Liveness check. Returns a static ok — no dependency checks yet."""
    return {"status": "ok"}
