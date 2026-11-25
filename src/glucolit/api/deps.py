"""Shared FastAPI dependencies."""

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from glucolit.db.llm_calls import LLMCallRepository
from glucolit.db.repository import DocumentRepository
from glucolit.db.session import AsyncSessionLocal
from glucolit.llm.gateway import LLMGateway


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


def get_gateway(request: Request) -> LLMGateway:
    """Provide the configured LLM gateway."""
    return request.app.state.gateway


def get_usage_repository() -> LLMCallRepository:
    """Provide the LLM usage repository."""
    return LLMCallRepository(AsyncSessionLocal)


RepositoryDep = Annotated[
    DocumentRepository,
    Depends(get_repository),
]

GatewayDep = Annotated[
    LLMGateway,
    Depends(get_gateway),
]

UsageDep = Annotated[
    LLMCallRepository,
    Depends(get_usage_repository),
]
