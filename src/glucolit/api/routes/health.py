"""Health and readiness endpoints."""

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/ready")
def ready(request: Request):
    records_loaded = request.app.state.records_loaded

    if not records_loaded:
        raise HTTPException(
            status_code=503,
            detail="Data file is not ready",
        )

    return {
        "status": "ready",
        "checks": {
            "records_loaded": True,
        },
    }
