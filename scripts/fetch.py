"""Command-line interface for fetching GlucoLit research papers."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from glucolit.ingest.fetch import fetch_all, read_sources  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch permitted GlucoLit research papers.")

    parser.add_argument(
        "door",
        choices=["urls"],
        help="Source collection method.",
    )

    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Minimum delay between requests to the same host.",
    )

    args = parser.parse_args()

    if args.delay < 0:
        parser.error("--delay cannot be negative")

    try:
        sources = read_sources()
        print(f"Found {len(sources)} paper sources.")

        downloaded = asyncio.run(fetch_all(sources, delay=args.delay))

        print(f"Completed: {downloaded}/{len(sources)} papers.")

    except KeyboardInterrupt:
        print("\nDownload interrupted. You can run the command again to resume.")
        sys.exit(130)

    except Exception as exc:
        print(f"Fetch failed: {exc}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
