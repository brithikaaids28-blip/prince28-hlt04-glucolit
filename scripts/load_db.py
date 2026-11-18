"""Load sample research records into PostgreSQL.

New records are inserted, changed records are updated,
and unchanged records are skipped using SHA-256 fingerprints.
"""

import asyncio
import hashlib
import json
from datetime import date

from sqlalchemy import select, update

from glucolit.config import get_settings
from glucolit.db.models import Document
from glucolit.db.session import AsyncSessionLocal, engine

# Use PMCID as the stable unique identifier.
ID_FIELD = "pmcid"

KNOWN = {
    "id",
    "pmcid",
    "title",
    "source_url",
    "licence",
    "doc_type",
    "published_on",
}


def fingerprint(record: dict) -> str:
    """Generate a stable SHA-256 fingerprint."""
    canonical = json.dumps(
        record,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def to_row(record: dict) -> dict:
    """Convert a JSON record into a database row."""
    published = record.get("published_on")

    return {
        "external_id": str(record[ID_FIELD]),
        "title": str(record["title"]),
        "source_url": record.get("source_url"),
        "licence": record.get("licence"),
        "doc_type": record.get("doc_type") or "record",
        "published_on": date.fromisoformat(published) if published else None,
        "sha256": fingerprint(record),
        "metadata_": {key: value for key, value in record.items() if key not in KNOWN},
    }


async def main() -> None:
    """Insert, update, or skip research records."""
    settings = get_settings()

    records = json.loads(settings.data_file.read_text(encoding="utf-8"))

    inserted = 0
    updated = 0
    unchanged = 0

    try:
        async with AsyncSessionLocal() as session, session.begin():
            result = await session.execute(select(Document.external_id, Document.sha256))
            existing = dict(result.all())

            for record in records:
                row = to_row(record)
                external_id = row["external_id"]
                old_hash = existing.get(external_id)

                if old_hash is None:
                    session.add(Document(**row))
                    inserted += 1

                elif old_hash != row["sha256"]:
                    await session.execute(
                        update(Document).where(Document.external_id == external_id).values(**row)
                    )
                    updated += 1

                else:
                    unchanged += 1

    finally:
        await engine.dispose()

    print(f"records={len(records)} inserted={inserted} updated={updated} unchanged={unchanged}")


if __name__ == "__main__":
    asyncio.run(main())
