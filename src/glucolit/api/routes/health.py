"""Health and readiness endpoints."""

from fastapi import APIRouter, HTTPException

from glucolit.api.deps import check_database

router = APIRouter()


@router.get("/health")
async def health():
    """Check whether the application is running."""
    return {"status": "ok"}


@router.get("/ready")
async def ready():
    """Check whether the database is available."""
    database_ready = await check_database()

    if not database_ready:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "not ready",
                "checks": {
                    "database": False,
                },
            },
        )

    return {
        "status": "ready",
        "checks": {
            "database": True,
        },
    }
