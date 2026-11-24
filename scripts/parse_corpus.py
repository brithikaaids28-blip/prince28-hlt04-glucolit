"""Parse downloaded GlucoLit articles and store documents and pages."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy import select  # noqa: E402

from glucolit.db.models import ParseFailure  # noqa: E402
from glucolit.db.session import AsyncSessionLocal, engine  # noqa: E402
from glucolit.ingest.fetch import MANIFEST, RAW, get_pmcid  # noqa: E402
from glucolit.ingest.parse import parse_file  # noqa: E402
from glucolit.ingest.store import store_failure, store_parsed  # noqa: E402


def read_manifest() -> list[dict]:
    """Read the latest manifest entry for each source URL."""
    entries = {}

    with MANIFEST.open("r", encoding="utf-8") as file:
        for line in file:
            if line.strip():
                entry = json.loads(line)
                entries[entry["url"]] = entry

    return [entry for entry in entries.values() if entry.get("status") == "downloaded"]


async def main() -> None:
    parser = argparse.ArgumentParser(description="Parse downloaded GlucoLit research articles.")
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Maximum number of articles to process (0 means all).",
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="Retry only files previously recorded as parsing failures.",
    )

    args = parser.parse_args()

    if args.limit < 0:
        parser.error("--limit cannot be negative")

    entries = read_manifest()

    async with AsyncSessionLocal() as session:
        if args.retry_failed:
            result = await session.execute(select(ParseFailure.path))
            failed_paths = set(result.scalars().all())

            entries = [
                entry
                for entry in entries
                if str(RAW / Path(entry["filename"]).name) in failed_paths
            ]

    entries = [entry for entry in entries if (RAW / Path(entry["filename"]).name).is_file()]

    if args.limit:
        entries = entries[: args.limit]

    print(f"Articles selected: {len(entries)}")

    successful = 0
    failed = 0

    try:
        for number, entry in enumerate(entries, start=1):
            path = RAW / Path(entry["filename"]).name
            source_url = entry["url"]

            try:
                pmcid = get_pmcid(source_url)
                parsed = parse_file(path)

                async with AsyncSessionLocal() as session, session.begin():
                    await store_parsed(
                        session,
                        path,
                        parsed,
                        external_id=f"parsed:{pmcid}",
                        title=parsed.title or entry["title"],
                        source_url=source_url,
                        licence=entry["licence"],
                        sha256=entry["sha256"],
                    )

                successful += 1
                print(f"[{number}/{len(entries)}] OK: {pmcid} ({len(parsed.pages)} pages)")

            except Exception as exc:
                failed += 1

                async with AsyncSessionLocal() as session, session.begin():
                    await store_failure(
                        session,
                        path,
                        reason=type(exc).__name__,
                        detail=str(exc),
                        source_url=source_url,
                        sha256=entry.get("sha256"),
                    )

                print(f"[{number}/{len(entries)}] FAILED: {entry.get('title', path.name)}: {exc}")

    finally:
        await engine.dispose()

    print("\nParsing summary")
    print(f"Selected: {len(entries)}")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nParsing interrupted.")
        raise SystemExit(130) from None
