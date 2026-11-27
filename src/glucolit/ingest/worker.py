"""ARQ background worker for GlucoLit ingestion jobs."""

import asyncio
import logging
from uuid import uuid4

import httpx
from arq.connections import RedisSettings
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from glucolit.config import get_settings
from glucolit.db.llm_calls import LLMCallRepository
from glucolit.db.models import Document, IngestItem
from glucolit.db.session import AsyncSessionLocal, engine
from glucolit.ingest.fetch import (
    CONTACT,
    DELAY,
    MANIFEST,
    RAW,
    TIMEOUT,
    USER_AGENT,
    HostGate,
    Manifest,
    Robots,
    Source,
    download_one,
    filename_for,
    get_pmcid,
)
from glucolit.ingest.parse import ParseError, parse_file
from glucolit.ingest.store import file_sha256, store_failure, store_parsed
from glucolit.llm.extract import extract_metadata
from glucolit.llm.gateway import build_gateway
from glucolit.llm.prompts import PROMPTS_DIR, latest, read_prompt

log = logging.getLogger("glucolit.worker")

MAX_ARTICLE_CHARS = 4000
FIRST_PAGES = 2


async def record_usage(row: dict) -> None:
    """Save LLM usage records."""
    repository = LLMCallRepository(AsyncSessionLocal)
    usage = {
        "request_id": uuid4().hex,
        "latency_ms": 0,
        "fallback_used": False,
        **row,
    }
    await repository.record(usage)


class RateLimitedGateway:
    """Limit LLM request frequency."""

    def __init__(self, gateway, rpm: float):
        self.gateway = gateway
        self.interval = 60.0 / rpm
        self.last_call = 0.0

    async def generate(self, *args, **kwargs):
        now = asyncio.get_running_loop().time()
        wait = self.interval - (now - self.last_call)

        if self.last_call and wait > 0:
            await asyncio.sleep(wait)

        self.last_call = asyncio.get_running_loop().time()
        return await self.gateway.generate(*args, **kwargs)


def article_text(document: Document) -> str:
    """Build extraction input from the first two pages."""
    pages = sorted(document.pages, key=lambda page: page.page_no)
    content = "\n\n".join(page.text.strip() for page in pages[:FIRST_PAGES] if page.text.strip())
    return content[:MAX_ARTICLE_CHARS]


def save_metadata(document: Document, metadata: dict, version: str) -> None:
    """Merge extraction results without replacing parser metadata."""
    existing = dict(document.metadata_ or {})
    existing.update(metadata)
    existing["extraction_status"] = "success"
    existing["extraction_prompt_version"] = version
    document.metadata_ = existing


async def process_ingest_item(ctx: dict, item_id: int) -> None:
    """Download, parse, store, and extract metadata for one source item."""
    settings = get_settings()

    async with AsyncSessionLocal() as session:
        item = await session.get(IngestItem, item_id)

        if item is None:
            log.warning("Ingest item %s does not exist", item_id)
            return

        item.status = "processing"
        item.attempts = (item.attempts or 0) + 1
        item.error = ""
        await session.commit()

        record = item.record
        source = Source(
            url=record["url"],
            source=record["source"],
            licence=record["licence"],
            title=record["title"],
        )

    RAW.mkdir(parents=True, exist_ok=True)
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)

    manifest = ctx["manifest"]
    client = ctx["http_client"]
    robots = ctx["robots"]
    gate = ctx["host_gate"]

    path = RAW / filename_for(source.url)

    try:
        downloaded = await download_one(source, client, robots, gate, manifest)

        if not downloaded:
            raise RuntimeError("Source download failed or was not eligible")

        if not path.is_file():
            raise FileNotFoundError(f"Downloaded file not found: {path}")

        parsed = parse_file(path)
        digest = file_sha256(path)

        pmcid = get_pmcid(source.url)
        external_id = f"parsed:{pmcid}"

        async with AsyncSessionLocal() as session:
            await store_parsed(
                session,
                path,
                parsed,
                external_id=external_id,
                title=source.title,
                source_url=source.url,
                licence=source.licence,
                sha256=digest,
            )
            await session.commit()

        version = latest(PROMPTS_DIR, "extract")
        prompt = read_prompt(PROMPTS_DIR, version)

        base_gateway = build_gateway(settings, recorder=record_usage)

        if not base_gateway.providers:
            raise RuntimeError("No LLM providers are configured")

        gateway = RateLimitedGateway(base_gateway, settings.ingest_rpm)

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Document)
                .options(selectinload(Document.pages))
                .where(Document.external_id == external_id)
            )
            document = result.scalar_one()

            text = article_text(document)

            if text.strip():
                metadata, _ = await extract_metadata(
                    gateway,
                    prompt,
                    version,
                    text,
                    pmcid,
                )
                save_metadata(document, metadata.model_dump(), version)
            else:
                existing = dict(document.metadata_ or {})
                existing["extraction_status"] = "skipped_empty_text"
                document.metadata_ = existing

            await session.commit()

        async with AsyncSessionLocal() as session:
            item = await session.get(IngestItem, item_id)

            if item is not None:
                item.status = "done"
                item.pages = len(parsed.pages)
                item.error = ""
                await session.commit()

        log.info("Ingestion item %s completed", item_id)

    except ParseError as exc:
        log.exception("Parsing failed for ingestion item %s", item_id)

        async with AsyncSessionLocal() as session:
            await store_failure(
                session,
                path,
                reason=exc.reason,
                detail=exc.detail,
                source_url=source.url,
            )

            item = await session.get(IngestItem, item_id)

            if item is not None:
                item.status = "failed"
                item.error = str(exc)[:1000]

            await session.commit()

        raise

    except Exception as exc:
        log.exception("Ingestion item %s failed", item_id)

        async with AsyncSessionLocal() as session:
            item = await session.get(IngestItem, item_id)

            if item is not None:
                item.status = "failed"
                item.error = str(exc)[:1000]
                await session.commit()

        raise


async def process_ingest_job(ctx: dict, job_id: str) -> None:
    """Process unfinished items in an ingestion job sequentially."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(IngestItem)
            .where(
                IngestItem.job_id == job_id,
                IngestItem.status != "done",
            )
            .order_by(IngestItem.id)
        )
        item_ids = [item.id for item in result.scalars().all()]

    for item_id in item_ids:
        await process_ingest_item(ctx, item_id)

    log.info("Ingestion job %s completed", job_id)


async def startup(ctx: dict) -> None:
    """Create shared downloader resources for this worker process."""
    headers = {"User-Agent": f"{USER_AGENT} ({CONTACT})"}
    timeout = httpx.Timeout(TIMEOUT)
    limits = httpx.Limits(
        max_connections=1,
        max_keepalive_connections=1,
    )

    client = httpx.AsyncClient(
        headers=headers,
        timeout=timeout,
        limits=limits,
        follow_redirects=True,
    )

    ctx["http_client"] = client
    ctx["robots"] = Robots(client)
    ctx["host_gate"] = HostGate(DELAY)
    ctx["manifest"] = Manifest(MANIFEST)

    log.info("GlucoLit ingestion worker started")


async def shutdown(ctx: dict) -> None:
    """Close worker resources."""
    client = ctx.get("http_client")

    if client is not None:
        await client.aclose()

    await engine.dispose()
    log.info("GlucoLit ingestion worker stopped")


class WorkerSettings:
    """ARQ worker configuration."""

    functions = [process_ingest_job]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 1
    job_timeout = get_settings().ingest_job_timeout
    max_tries = get_settings().ingest_max_tries
