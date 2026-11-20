from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from glucolit.config import get_settings
from glucolit.db.session import AsyncSessionLocal

router = APIRouter()


async def check_database() -> bool:
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@router.api_route("/health", methods=["GET", "HEAD"])
def health():
    settings = get_settings()
    return {
        "status": "ok",
        "app": settings.app_name,
        "env": settings.app_env,
        "version": settings.git_sha,
    }


@router.get("/ready")
async def ready():
    database_ready = await check_database()

    if not database_ready:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "not ready",
                "checks": {"database": False},
            },
        )

    return {
        "status": "ready",
        "checks": {"database": True},
    }
