"""Shared FastAPI dependencies."""

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from glucolit.db.repository import DocumentRepository
from glucolit.db.session import AsyncSessionLocal


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide one database session per request."""
    async with AsyncSessionLocal() as session:
        yield session


async def get_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DocumentRepository:
    """Provide a document repository using the request session."""
    return DocumentRepository(session)


async def check_database() -> bool:
    """Check whether the database is reachable."""
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


RepositoryDep = Annotated[
    DocumentRepository,
    Depends(get_repository),
]
