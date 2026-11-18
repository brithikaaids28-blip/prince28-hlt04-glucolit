"""Show how Postgres uses the GIN index for JSONB filtering."""

import asyncio
import json
import sys

from sqlalchemy import text

from glucolit.db.session import engine

SQL = """
EXPLAIN ANALYZE
SELECT id, title
FROM documents
WHERE metadata @> CAST(:f AS jsonb)
"""


async def main(field: str, value: str) -> None:
    params = {"f": json.dumps({field: value})}

    try:
        async with engine.connect() as conn:
            print("-- 1) What the planner chooses on its own:")

            result = await conn.execute(text(SQL), params)
            for line in result.scalars():
                print(line)

            await conn.execute(text("SET enable_seqscan = off"))

            print("\n-- 2) Seq scan switched off:")

            result = await conn.execute(text(SQL), params)
            for line in result.scalars():
                print(line)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("Usage: uv run python scripts/explain.py <field> <value>")

    asyncio.run(main(sys.argv[1], sys.argv[2]))
