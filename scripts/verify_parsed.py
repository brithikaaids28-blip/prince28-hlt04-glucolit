"""Verify parsed GlucoLit documents, pages, and failures."""

import asyncio

from sqlalchemy import func, select

from glucolit.db.models import Document, Page, ParseFailure
from glucolit.db.session import AsyncSessionLocal, engine


async def main():
    try:
        async with AsyncSessionLocal() as session:
            documents = await session.scalar(
                select(func.count())
                .select_from(Document)
                .where(Document.external_id.like("parsed:%"))
            )

            pages = await session.scalar(
                select(func.count())
                .select_from(Page)
                .join(Document)
                .where(Document.external_id.like("parsed:%"))
            )

            failures = await session.scalar(select(func.count()).select_from(ParseFailure))

            print("Parsed documents:", documents)
            print("Parsed pages:", pages)
            print("Parsing failures:", failures)

    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
