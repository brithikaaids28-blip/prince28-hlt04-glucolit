import asyncio
import os

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from glucolit.db.models import Base, Document
from glucolit.db.repository import DocumentRepository
from glucolit.db.url import to_asyncpg_url

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not configured",
)


@pytest.fixture
def db_engine():
    engine = create_async_engine(
        to_asyncpg_url(TEST_DATABASE_URL),
        pool_pre_ping=True,
    )

    async def setup():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)

        async with async_sessionmaker(engine)() as session:
            session.add_all(
                [
                    Document(
                        external_id="TEST-001",
                        title="Integration Alpha",
                        doc_type="record",
                        sha256="a" * 64,
                        metadata_={"year": 2024, "kind": "guideline"},
                    ),
                    Document(
                        external_id="TEST-002",
                        title="Integration Beta",
                        doc_type="record",
                        sha256="b" * 64,
                        metadata_={"year": 2025, "kind": "circular"},
                    ),
                ]
            )
            await session.commit()

    asyncio.run(setup())

    yield engine

    async def teardown():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
        await engine.dispose()

    asyncio.run(teardown())


@pytest.fixture
def repository(db_engine):
    session_factory = async_sessionmaker(
        db_engine,
        expire_on_commit=False,
    )

    async def run_list(**kwargs):
        async with session_factory() as session:
            return await DocumentRepository(session).list(**kwargs)

    async def run_get(external_id):
        async with session_factory() as session:
            return await DocumentRepository(session).get(external_id)

    return run_list, run_get


def test_database_lists_documents(repository):
    run_list, _ = repository

    total, documents = asyncio.run(run_list(q=None, filters={}, limit=10, offset=0))

    assert total == 2
    assert len(documents) == 2


def test_database_filters_metadata(repository):
    run_list, _ = repository

    total, documents = asyncio.run(
        run_list(
            q=None,
            filters={"year": "2024"},
            limit=10,
            offset=0,
        )
    )

    assert total == 1
    assert documents[0]["id"] == "TEST-001"


def test_database_get_document(repository):
    _, run_get = repository

    document = asyncio.run(run_get("TEST-001"))

    assert document is not None
    assert document["title"] == "Integration Alpha"
