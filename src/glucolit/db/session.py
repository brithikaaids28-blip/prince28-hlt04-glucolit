"""Async database engine and session factory."""

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from glucolit.config import get_settings
from glucolit.db.url import to_asyncpg_url

settings = get_settings()

engine = create_async_engine(
    to_asyncpg_url(settings.database_url),
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)
