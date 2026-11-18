"""Idempotently load sample research records into PostgreSQL."""

import asyncio
import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from glucolit.db.models import Document
from glucolit.db.session import AsyncSessionLocal

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RECORDS_FILE = PROJECT_ROOT / "data" / "sample_records.json"


def calculate_sha256(record: dict[str, Any]) -> str:
    """Calculate a stable SHA-256 hash for a record."""
    content = json.dumps(
        record,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


async def load_record(
    session: AsyncSession,
    record: dict[str, Any],
) -> None:
    """Insert a new record or update an existing one."""
    metadata_fields = {
        key: value
        for key, value in record.items()
        if key
        not in {
            "id",
            "pmcid",
            "title",
            "source_url",
            "licence",
            "published_on",
        }
    }

    published_on = record.get("published_on")
    if published_on:
        published_on = date.fromisoformat(published_on)

    values = {
        "external_id": record["pmcid"],
        "title": record["title"],
        "source_url": record.get("source_url"),
        "licence": record.get("licence"),
        "doc_type": "record",
        "published_on": published_on,
        "sha256": calculate_sha256(record),
        "metadata_": metadata_fields,
    }

    statement = insert(Document).values(**values)

    statement = statement.on_conflict_do_update(
        index_elements=[Document.external_id],
        set_={
            "title": statement.excluded.title,
            "source_url": statement.excluded.source_url,
            "licence": statement.excluded.licence,
            "published_on": statement.excluded.published_on,
            "sha256": statement.excluded.sha256,
            "metadata": statement.excluded.metadata,
            "updated_at": statement.excluded.updated_at,
        },
    )

    await session.execute(statement)


async def main() -> None:
    """Load all sample records into the database."""
    with RECORDS_FILE.open("r", encoding="utf-8") as file:
        records = json.load(file)

    async with AsyncSessionLocal() as session:
        try:
            for record in records:
                await load_record(session, record)

            await session.commit()
            print(f"Successfully loaded {len(records)} records.")

        except Exception:
            await session.rollback()
            raise


if __name__ == "__main__":
    asyncio.run(main())
