import asyncio

from sqlalchemy import func, select

from glucolit.db.models import Document
from glucolit.db.session import AsyncSessionLocal, engine


async def main():
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(func.count()).select_from(Document))
        count = result.scalar_one()

        print(f"Total records in database: {count}")

        records = await session.execute(select(Document.external_id, Document.title))

        for external_id, title in records:
            print(f"{external_id}: {title}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
