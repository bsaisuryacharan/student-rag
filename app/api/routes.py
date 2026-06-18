# app/api/routes.py
import logging
from fastapi import APIRouter, Request, Response, status

logger = logging.getLogger("app.system")
router = APIRouter(tags=["system"])

@router.get("/health")
async def health() -> dict:
    # Liveness: the process is up. No external calls — keep it instant.
    return {"status": "ok"}

# Readiness: the process is up and can connect to dependencies. We check OpenAI key presence and Qdrant connectivity. This is a more expensive check, so it's separate from /health.
@router.get("/ready")
async def ready(request: Request, response: Response) -> dict:
    settings = request.app.state.settings
    checks = {"openai_key": bool(settings.openai_api_key), "qdrant": False}
    try:
        await request.app.state.qdrant.get_collections()
        checks["qdrant"] = True
    except Exception as exc:                       # noqa: BLE001
        logger.warning("Qdrant readiness check failed: %s", exc)

    ok = all(checks.values())
    if not ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ready" if ok else "not_ready", "checks": checks}
