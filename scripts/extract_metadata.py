"""Extract structured metadata from parsed GlucoLit documents."""

import argparse
import asyncio
import hashlib
import json
import logging
import time
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from glucolit.config import get_settings
from glucolit.db.llm_calls import LLMCallRepository
from glucolit.db.models import Document
from glucolit.db.session import AsyncSessionLocal, engine
from glucolit.llm.extract import extract_metadata
from glucolit.llm.gateway import LLMUnavailable, build_gateway
from glucolit.llm.prompts import PROMPTS_DIR, latest, read_prompt

log = logging.getLogger("extract_metadata")

ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "eval" / "cache"
MAX_UNAVAILABLE_ERRORS = 2
MAX_ARTICLE_CHARS = 4000
FIRST_PAGES = 2


class RateLimitedGateway:
    """Apply requests-per-minute pacing to every model request."""

    def __init__(self, gateway, rpm: int):
        self.gateway = gateway
        self.interval = 60.0 / rpm
        self.last_call = 0.0

    async def generate(self, *args, **kwargs):
        now = time.monotonic()
        wait = self.interval - (now - self.last_call)

        if self.last_call and wait > 0:
            await asyncio.sleep(wait)

        self.last_call = time.monotonic()
        return await self.gateway.generate(*args, **kwargs)


def sha256_text(value: str) -> str:
    """Return the SHA-256 hash of text."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def load_cache(path: Path) -> dict:
    """Load the extraction cache."""
    if not path.exists():
        return {}

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("Could not read cache %s: %s", path, exc)
        return {}


def save_cache(path: Path, cache: dict) -> None:
    """Save cache atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)

    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(cache, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    temporary.replace(path)


def article_text(document: Document) -> str:
    """Combine the first few pages of a document."""
    pages = sorted(document.pages, key=lambda page: page.page_no)

    text = "\n\n".join(page.text.strip() for page in pages[:FIRST_PAGES] if page.text.strip())

    return text[:MAX_ARTICLE_CHARS]


def document_pmcid(document: Document) -> str:
    """Get the PMC identifier from the parsed document ID."""
    external_id = document.external_id

    if external_id.startswith("parsed:"):
        external_id = external_id.removeprefix("parsed:")

    return external_id


def save_metadata(document: Document, metadata: dict, version: str) -> None:
    """Merge extracted metadata without replacing parser metadata."""
    existing = dict(document.metadata_ or {})
    existing.update(metadata)

    existing["extraction_status"] = "success"
    existing["extraction_prompt_version"] = version

    document.metadata_ = existing


async def record_usage(row: dict) -> None:
    """Add the required request ID before storing LLM usage."""
    repository = LLMCallRepository(AsyncSessionLocal)

    usage = {
        "request_id": uuid4().hex,
        "latency_ms": 0,
        "fallback_used": False,
        **row,
    }

    await repository.record(usage)


async def run(args) -> int:
    settings = get_settings()

    version = args.prompt_version or latest(PROMPTS_DIR, "extract")
    prompt = read_prompt(PROMPTS_DIR, version)
    prompt_hash = sha256_text(prompt)

    cache_path = CACHE_DIR / f"extract_{version}.json"
    cache = load_cache(cache_path)

    base_gateway = build_gateway(settings, recorder=record_usage)

    if not base_gateway.providers:
        print("ERROR: No LLM providers configured. Check your API keys.")
        return 1

    gateway = RateLimitedGateway(base_gateway, args.rpm)

    processed = 0
    succeeded = 0
    failed = 0
    skipped = 0
    unavailable_errors = 0

    async with AsyncSessionLocal() as session:
        statement = select(Document).options(selectinload(Document.pages)).order_by(Document.id)

        result = await session.execute(statement)
        documents = result.scalars().unique().all()

        for document in documents:
            if args.limit is not None and processed >= args.limit:
                break

            if not document.pages:
                continue

            current_metadata = document.metadata_ or {}

            if (
                current_metadata.get("extraction_status") == "success"
                and current_metadata.get("extraction_prompt_version") == version
            ):
                skipped += 1
                continue

            text = article_text(document)

            if not text.strip():
                skipped += 1
                continue

            pmcid = document_pmcid(document)

            input_hash = sha256_text(text)
            external_id = document.external_id

            cached = cache.get(external_id, {})

            cache_matches = (
                cached.get("input_sha256") == input_hash
                and cached.get("prompt_sha256") == prompt_hash
            )

            if cache_matches and cached.get("status") == "success":
                save_metadata(
                    document,
                    cached["metadata"],
                    version,
                )
                await session.commit()
                succeeded += 1
                processed += 1
                print(f"CACHED: {external_id}")
                continue

            if cache_matches and cached.get("status") == "failed" and not args.retry_failed:
                skipped += 1
                continue

            processed += 1
            print(f"[{processed}] Extracting {external_id}...")

            try:
                metadata, llm_result = await extract_metadata(
                    gateway,
                    prompt,
                    version,
                    text,
                    pmcid,
                )

                extracted = metadata.model_dump()

                save_metadata(document, extracted, version)
                await session.commit()

                cache[external_id] = {
                    "status": "success",
                    "input_sha256": input_hash,
                    "prompt_sha256": prompt_hash,
                    "metadata": extracted,
                }
                save_cache(cache_path, cache)

                succeeded += 1
                unavailable_errors = 0

                print(
                    f"SUCCESS: {external_id} | "
                    f"{llm_result.provider} | "
                    f"{llm_result.tokens_in} input tokens | "
                    f"{llm_result.tokens_out} output tokens | "
                    f"₹{llm_result.cost_inr}"
                )

            except LLMUnavailable as exc:
                await session.rollback()

                failed += 1
                unavailable_errors += 1

                cache[external_id] = {
                    "status": "failed",
                    "input_sha256": input_hash,
                    "prompt_sha256": prompt_hash,
                    "error": str(exc)[:1000],
                }
                save_cache(cache_path, cache)

                print(f"PROVIDER ERROR: {external_id}: {exc}")

                if unavailable_errors >= MAX_UNAVAILABLE_ERRORS:
                    print("Stopping: two consecutive provider-unavailable errors occurred.")
                    break

            except Exception as exc:
                await session.rollback()

                failed += 1
                unavailable_errors = 0

                cache[external_id] = {
                    "status": "failed",
                    "input_sha256": input_hash,
                    "prompt_sha256": prompt_hash,
                    "error": str(exc)[:1000],
                }
                save_cache(cache_path, cache)

                log.exception("Extraction failed for %s", external_id)
                print(f"FAILED: {external_id}: {exc}")

    print("\nExtraction summary")
    print("------------------")
    print(f"Prompt version: {version}")
    print(f"Processed:      {processed}")
    print(f"Successful:     {succeeded}")
    print(f"Failed:         {failed}")
    print(f"Skipped:        {skipped}")
    print(f"Cache:          {cache_path}")

    return 0


async def run_and_dispose(args) -> int:
    """Run extraction and dispose the engine on the same event loop."""
    try:
        return await run(args)
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract metadata from parsed GlucoLit documents.")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of documents to process.",
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="Retry documents with cached extraction failures.",
    )
    parser.add_argument(
        "--rpm",
        type=int,
        default=10,
        help="Maximum LLM requests per minute (default: 10).",
    )
    parser.add_argument(
        "--prompt-version",
        default=None,
        help="Prompt version, for example extract_v2.",
    )

    args = parser.parse_args()

    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1.")

    if args.rpm < 1:
        parser.error("--rpm must be at least 1.")

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    exit_code = asyncio.run(run_and_dispose(args))
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
