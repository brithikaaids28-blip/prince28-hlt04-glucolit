"""Store parsed GlucoLit documents, pages, and parsing failures."""

from __future__ import annotations

import hashlib
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from glucolit.db.models import Document, Page, ParseFailure
from glucolit.ingest.parse import ParsedDoc


def file_sha256(path: Path) -> str:
    """Calculate the SHA-256 hash of a file."""
    digest = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


async def store_parsed(
    session: AsyncSession,
    path: Path,
    parsed: ParsedDoc,
    *,
    external_id: str,
    title: str,
    source_url: str | None = None,
    licence: str | None = None,
    sha256: str | None = None,
) -> None:
    """Save a parsed document and replace its existing pages."""
    path = Path(path)
    digest = sha256 or file_sha256(path)

    values = {
        "external_id": external_id,
        "title": title,
        "source_url": source_url,
        "licence": licence,
        "doc_type": parsed.kind,
        "sha256": digest,
        "metadata_": {
            "parser": parsed.parser,
            "pages": len(parsed.pages),
            "tables": sum(page.tables for page in parsed.pages),
            "path": str(path),
        },
    }

    statement = insert(Document).values(**values)
    statement = statement.on_conflict_do_update(
        index_elements=[Document.external_id],
        set_={
            "title": statement.excluded.title,
            "source_url": statement.excluded.source_url,
            "licence": statement.excluded.licence,
            "doc_type": statement.excluded.doc_type,
            "sha256": statement.excluded.sha256,
            "metadata": statement.excluded.metadata,
            "updated_at": statement.excluded.updated_at,
        },
    )

    await session.execute(statement)

    result = await session.execute(
        __import__("sqlalchemy").select(Document.id).where(Document.external_id == external_id)
    )
    document_id = result.scalar_one()

    await session.execute(delete(Page).where(Page.document_id == document_id))

    for page in parsed.pages:
        session.add(
            Page(
                document_id=document_id,
                page_no=page.page_no,
                text=page.text,
                headings=page.headings,
            )
        )

    await session.execute(delete(ParseFailure).where(ParseFailure.path == str(path)))


async def store_failure(
    session: AsyncSession,
    path: Path,
    *,
    reason: str,
    detail: str = "",
    source_url: str | None = None,
    sha256: str | None = None,
) -> None:
    """Record a parsing failure or update an existing failure."""
    path = Path(path)
    digest = sha256 or file_sha256(path)

    statement = insert(ParseFailure).values(
        path=str(path),
        sha256=digest,
        source_url=source_url,
        reason=reason,
        detail=detail[:500],
        attempts=1,
    )

    statement = statement.on_conflict_do_update(
        index_elements=[ParseFailure.path],
        set_={
            "sha256": statement.excluded.sha256,
            "source_url": statement.excluded.source_url,
            "reason": statement.excluded.reason,
            "detail": statement.excluded.detail,
            "attempts": ParseFailure.attempts + 1,
            "updated_at": statement.excluded.updated_at,
        },
    )

    await session.execute(statement)
