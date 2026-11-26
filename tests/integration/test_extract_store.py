"""Integration tests for extracted metadata storage."""

import pytest
from sqlalchemy import select

from glucolit.db.models import Document
from glucolit.db.session import make_engine, make_sessionmaker
from scripts.extract_metadata import save_metadata


@pytest.mark.asyncio
async def test_save_metadata_preserves_parser_metadata(database_url):
    """Extracted metadata must merge with existing parser metadata."""
    engine = make_engine(
        type(
            "Settings",
            (),
            {
                "database_url": database_url,
            },
        )()
    )

    extracted_metadata = {
        "doc_kind": "research_article",
        "year": 2025,
        "language": "English",
        "summary": "A study examining diabetes management and glycemic control.",
        "topics": ["diabetes", "glycemic control"],
        "pmcid": "PMC12345678",
        "journal": "Scientific Reports",
        "study_type": "Cross-sectional study",
        "population": "Adults with type 2 diabetes.",
        "sample_size": 250,
    }

    try:
        async with make_sessionmaker(engine)() as session:
            async with session.begin():
                document = Document(
                    external_id="parsed:PMC12345678",
                    title="Test diabetes research article",
                    doc_type="text",
                    sha256="a" * 64,
                    metadata_={
                        "parser": "test-parser",
                        "pages": 3,
                        "tables": 1,
                        "path": "test-paper.xml",
                    },
                )
                session.add(document)
                await session.flush()

                save_metadata(document, extracted_metadata, "extract_v2")

            document_id = document.id

        async with make_sessionmaker(engine)() as session:
            stored = await session.scalar(select(Document).where(Document.id == document_id))

        assert stored is not None

        # Existing parser metadata must remain.
        assert stored.metadata_["parser"] == "test-parser"
        assert stored.metadata_["pages"] == 3
        assert stored.metadata_["tables"] == 1
        assert stored.metadata_["path"] == "test-paper.xml"

        # Extracted metadata must be stored.
        assert stored.metadata_["pmcid"] == "PMC12345678"
        assert stored.metadata_["doc_kind"] == "research_article"
        assert stored.metadata_["sample_size"] == 250

        # Extraction tracking fields must be stored.
        assert stored.metadata_["extraction_status"] == "success"
        assert stored.metadata_["extraction_prompt_version"] == "extract_v2"

    finally:
        await engine.dispose()
