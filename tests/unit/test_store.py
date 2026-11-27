"""Tests for idempotent parsed-document storage."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from glucolit.db.models import Page
from glucolit.ingest.parse import ParsedDoc, ParsedPage
from glucolit.ingest.store import file_sha256, store_parsed


def make_session(previous_digest, document_id=42):
    """Create a mocked async database session."""
    previous_result = MagicMock()
    previous_result.scalar_one_or_none.return_value = previous_digest

    document_result = MagicMock()
    document_result.scalar_one.return_value = document_id

    session = MagicMock()
    session.execute = AsyncMock(
        side_effect=[previous_result, MagicMock(), document_result, MagicMock(), MagicMock()]
    )
    session.add = MagicMock()

    return session


def make_parsed_doc():
    """Create a small parsed document for testing."""
    return ParsedDoc(
        parser="test-parser",
        kind="xml",
        title="Test paper",
        pages=[
            ParsedPage(
                page_no=1,
                text="First page text",
                headings=["Introduction"],
                tables=0,
            ),
            ParsedPage(
                page_no=2,
                text="Second page text",
                headings=["Methods"],
                tables=1,
            ),
        ],
    )


@pytest.mark.asyncio
async def test_store_parsed_inserts_pages_for_new_document(tmp_path):
    path = tmp_path / "paper.xml"
    path.write_text("<article>test</article>", encoding="utf-8")
    digest = file_sha256(path)

    session = make_session(previous_digest=None)

    await store_parsed(
        session,
        path,
        make_parsed_doc(),
        external_id="PMC123456",
        title="Test paper",
        sha256=digest,
    )

    added_pages = [
        call.args[0] for call in session.add.call_args_list if isinstance(call.args[0], Page)
    ]

    assert len(added_pages) == 2
    assert added_pages[0].page_no == 1
    assert added_pages[1].page_no == 2
    assert added_pages[0].text == "First page text"


@pytest.mark.asyncio
async def test_store_parsed_does_not_rewrite_pages_when_hash_is_unchanged(
    tmp_path,
):
    path = tmp_path / "paper.xml"
    path.write_text("<article>unchanged</article>", encoding="utf-8")
    digest = file_sha256(path)

    session = make_session(previous_digest=digest)

    await store_parsed(
        session,
        path,
        make_parsed_doc(),
        external_id="PMC123456",
        title="Test paper",
        sha256=digest,
    )

    added_pages = [
        call.args[0] for call in session.add.call_args_list if isinstance(call.args[0], Page)
    ]

    # Existing pages should remain untouched on an unchanged-file retry.
    assert added_pages == []

    # The upsert should merge parser metadata with existing JSONB metadata.
    upsert_statement = session.execute.await_args_list[1].args[0]
    sql = str(upsert_statement.compile(dialect=postgresql.dialect()))

    assert "metadata" in sql
    assert "||" in sql


@pytest.mark.asyncio
async def test_store_parsed_replaces_pages_when_hash_changes(tmp_path):
    path = tmp_path / "paper.xml"
    path.write_text("<article>new version</article>", encoding="utf-8")
    digest = file_sha256(path)

    session = make_session(previous_digest="old-file-hash")

    await store_parsed(
        session,
        path,
        make_parsed_doc(),
        external_id="PMC123456",
        title="Updated test paper",
        sha256=digest,
    )

    added_pages = [
        call.args[0] for call in session.add.call_args_list if isinstance(call.args[0], Page)
    ]

    assert len(added_pages) == 2

    # Five database operations: previous hash, upsert, document ID,
    # delete old pages, and clear any previous parse failure.
    assert session.execute.await_count == 5
