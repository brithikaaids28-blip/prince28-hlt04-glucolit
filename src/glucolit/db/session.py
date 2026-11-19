"""Async database engine and session factory."""

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from glucolit.config import Settings, get_settings
from glucolit.db.url import to_asyncpg_url


def make_engine(settings: Settings | None = None):
    """Create an async database engine."""
    settings = settings or get_settings()
    return create_async_engine(
        to_asyncpg_url(settings.database_url),
        pool_pre_ping=True,
    )


def make_sessionmaker(engine):
    """Create an async session factory for an engine."""
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


engine = make_engine()
AsyncSessionLocal = make_sessionmaker(engine)
