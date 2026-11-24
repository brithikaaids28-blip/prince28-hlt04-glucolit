import pytest
from sqlalchemy import select

from glucolit.db.models import Document, Page, ParseFailure
from glucolit.db.session import make_engine, make_sessionmaker
from glucolit.ingest.parse import ParsedDoc, ParsedPage
from glucolit.ingest.store import store_failure, store_parsed


@pytest.fixture
def parsed_doc():
    return ParsedDoc(
        parser="test-parser",
        kind="text",
        title="Test research paper",
        pages=[
            ParsedPage(
                page_no=1,
                text="Introduction to diabetes research.",
                headings=["Introduction"],
            ),
            ParsedPage(
                page_no=2,
                text="Results of the study.",
                headings=["Results"],
            ),
        ],
    )


@pytest.mark.asyncio
async def test_store_parsed_document(database_url, tmp_path, parsed_doc):
    path = tmp_path / "paper.txt"
    path.write_text("Sample research paper", encoding="utf-8")

    engine = make_engine(
        type(
            "Settings",
            (),
            {
                "database_url": database_url,
            },
        )()
    )

    try:
        async with make_sessionmaker(engine)() as session, session.begin():
            await store_parsed(
                session,
                path,
                parsed_doc,
                external_id="parsed:TEST001",
                title="Test research paper",
                source_url="https://example.org/paper",
                licence="CC BY 4.0",
            )

        async with make_sessionmaker(engine)() as session:
            document = await session.scalar(
                select(Document).where(Document.external_id == "parsed:TEST001")
            )
            pages = (
                await session.scalars(
                    select(Page).where(Page.document_id == document.id).order_by(Page.page_no)
                )
            ).all()

        assert document is not None
        assert document.doc_type == "text"
        assert len(pages) == 2
        assert pages[0].headings == ["Introduction"]

    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_store_parsed_replaces_existing_pages(database_url, tmp_path, parsed_doc):
    path = tmp_path / "paper.txt"
    path.write_text("Sample research paper", encoding="utf-8")

    engine = make_engine(
        type(
            "Settings",
            (),
            {
                "database_url": database_url,
            },
        )()
    )

    try:
        async with make_sessionmaker(engine)() as session, session.begin():
            for _ in range(2):
                await store_parsed(
                    session,
                    path,
                    parsed_doc,
                    external_id="parsed:TEST002",
                    title="Test research paper",
                )

        async with make_sessionmaker(engine)() as session:
            document = await session.scalar(
                select(Document).where(Document.external_id == "parsed:TEST002")
            )
            pages = (
                await session.scalars(select(Page).where(Page.document_id == document.id))
            ).all()

        assert document is not None
        assert len(pages) == 2

    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_store_failure_tracks_retry_attempts(database_url, tmp_path):
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"broken PDF")

    engine = make_engine(
        type(
            "Settings",
            (),
            {
                "database_url": database_url,
            },
        )()
    )

    try:
        async with make_sessionmaker(engine)() as session, session.begin():
            await store_failure(
                session,
                path,
                reason="corrupt_pdf",
                detail="Could not read PDF",
            )
            await store_failure(
                session,
                path,
                reason="corrupt_pdf",
                detail="Still cannot read PDF",
            )

        async with make_sessionmaker(engine)() as session:
            failure = await session.scalar(
                select(ParseFailure).where(ParseFailure.path == str(path))
            )

        assert failure is not None
        assert failure.attempts == 2
        assert failure.reason == "corrupt_pdf"

    finally:
        await engine.dispose()
