"""Polite PMC OAI-PMH downloader for GlucoLit."""

from __future__ import annotations

import asyncio
import csv
import hashlib
import json
import logging
import random
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx
from protego import Protego

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "data"
RAW = DATA / "raw"
SOURCES = DATA / "sources.csv"
MANIFEST = DATA / "manifest.jsonl"

OAI_ENDPOINT = "https://pmc.ncbi.nlm.nih.gov/api/oai/v1/mh/"
USER_AGENT = "GlucoLitResearchBot/1.0"
CONTACT = "https://github.com/brithikaaids28-blip/prince28-hlt04-glucolit"

DELAY = 1.0
TIMEOUT = 60.0
MAX_RETRIES = 3
MAX_BYTES = 50 * 1024 * 1024

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("glucolit.fetch")


@dataclass
class Source:
    url: str
    source: str
    licence: str
    title: str


@dataclass
class ManifestEntry:
    url: str
    title: str
    source: str
    licence: str
    filename: str
    sha256: str
    bytes: int
    downloaded_at: str
    status: str


def read_sources(path: Path = SOURCES) -> list[Source]:
    """Read source URLs and require a verified licence."""
    sources = []

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        rows = (line for line in file if line.strip() and not line.lstrip().startswith("#"))
        reader = csv.DictReader(rows)

        required = {"url", "source", "licence", "title"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("sources.csv must contain url, source, licence, title")

        for number, row in enumerate(reader, start=2):
            url = (row.get("url") or "").strip()
            name = (row.get("source") or "").strip()
            licence = (row.get("licence") or "").strip()
            title = (row.get("title") or "").strip()

            if not url or not name or not title:
                raise ValueError(f"sources row {number}: missing required field")

            if not licence or licence.upper() == "REVIEW_REQUIRED":
                raise ValueError(f"sources row {number}: verified licence required")

            if urlparse(url).scheme != "https":
                raise ValueError(f"sources row {number}: HTTPS URL required")

            sources.append(Source(url, name, licence, title))

    return sources


def get_pmcid(url: str) -> str:
    """Extract the PMC identifier from an article URL."""
    match = re.search(r"PMC(\d+)", url, re.IGNORECASE)

    if not match:
        raise ValueError(f"Could not find a PMCID in URL: {url}")

    return f"PMC{match.group(1)}"


def filename_for(url: str) -> str:
    """Generate a stable XML filename."""
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    return f"{digest}.xml"


class Manifest:
    """Track downloaded documents."""

    def __init__(self, path: Path = MANIFEST):
        self.path = path
        self.entries: dict[str, dict] = {}
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            return

        with self.path.open("r", encoding="utf-8") as file:
            for line in file:
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                    self.entries[entry["url"]] = entry
                except (json.JSONDecodeError, KeyError):
                    log.warning("Ignoring invalid manifest line")

    def contains(self, url: str) -> bool:
        entry = self.entries.get(url)
        if not entry:
            return False

        file_path = RAW / entry.get("filename", "")
        return (
            entry.get("status") == "downloaded"
            and file_path.is_file()
            and file_path.stat().st_size == entry.get("bytes")
        )

    def add(self, entry: ManifestEntry) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)

        record = asdict(entry)
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")

        self.entries[entry.url] = record


class Robots:
    """Check and cache robots.txt rules."""

    def __init__(self, client: httpx.AsyncClient):
        self.client = client
        self.cache: dict[str, Protego] = {}

    async def allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"

        if origin not in self.cache:
            try:
                response = await self.client.get(f"{origin}/robots.txt")

                if response.status_code == 200:
                    rules = Protego.parse(response.text)
                elif response.status_code in (404, 410):
                    rules = Protego.parse("")
                else:
                    log.warning(
                        "Cannot verify robots.txt for %s: HTTP %s",
                        origin,
                        response.status_code,
                    )
                    return False

                self.cache[origin] = rules

            except httpx.HTTPError as exc:
                log.warning("Robots check failed: %s", exc)
                return False

        return self.cache[origin].can_fetch(url, USER_AGENT)


class HostGate:
    """Space requests to the same host."""

    def __init__(self, delay: float):
        self.delay = delay
        self.last_request: dict[str, float] = {}

    async def wait(self, url: str) -> None:
        host = urlparse(url).netloc
        now = time.monotonic()
        previous = self.last_request.get(host, 0.0)
        wait_time = self.delay - (now - previous)

        if wait_time > 0:
            await asyncio.sleep(wait_time)

        self.last_request[host] = time.monotonic()


def has_article(xml_data: bytes) -> bool:
    """Confirm the OAI response contains a JATS article."""
    try:
        root = ET.fromstring(xml_data)
    except ET.ParseError:
        return False

    return any(element.tag.split("}")[-1] == "article" for element in root.iter())


async def download_one(
    source: Source,
    client: httpx.AsyncClient,
    robots: Robots,
    gate: HostGate,
    manifest: Manifest,
) -> bool:
    """Retrieve one eligible article through PMC OAI-PMH."""

    if manifest.contains(source.url):
        log.info("Already downloaded: %s", source.title)
        return True

    # NoDerivatives licences do not permit adapting the full text.
    if "NC-ND" in source.licence.upper():
        log.warning("Skipping NoDerivatives article: %s", source.title)
        return False

    pmcid = get_pmcid(source.url)

    if not await robots.allowed(OAI_ENDPOINT):
        log.warning("PMC robots check did not permit retrieval")
        return False

    await gate.wait(OAI_ENDPOINT)

    params = {
        "verb": "GetRecord",
        "identifier": (f"oai:pubmedcentral.nih.gov:{pmcid.removeprefix('PMC')}"),
        "metadataPrefix": "pmc",
    }

    filename = filename_for(source.url)
    destination = RAW / filename
    partial = RAW / f"{filename}.part"

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = await client.get(
                OAI_ENDPOINT,
                params=params,
                headers={"Accept": "application/xml"},
            )
            response.raise_for_status()

            xml_data = response.content

            if not xml_data:
                raise ValueError("PMC returned an empty response")

            if len(xml_data) > MAX_BYTES:
                raise ValueError("Article exceeds 50 MB limit")

            if not has_article(xml_data):
                raise ValueError(f"No reusable full-text article returned for {pmcid}")

            partial.write_bytes(xml_data)
            partial.replace(destination)

            entry = ManifestEntry(
                url=source.url,
                title=source.title,
                source=source.source,
                licence=source.licence,
                filename=filename,
                sha256=hashlib.sha256(xml_data).hexdigest(),
                bytes=len(xml_data),
                downloaded_at=time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ",
                    time.gmtime(),
                ),
                status="downloaded",
            )

            manifest.add(entry)
            log.info("Downloaded %s (%s bytes)", pmcid, len(xml_data))
            return True

        except (httpx.HTTPError, OSError, ValueError) as exc:
            partial.unlink(missing_ok=True)
            log.warning(
                "Attempt %s/%s failed for %s: %s",
                attempt,
                MAX_RETRIES,
                pmcid,
                exc,
            )

            if attempt < MAX_RETRIES:
                await asyncio.sleep((2**attempt) + random.random())

    log.error("Download failed: %s", pmcid)
    return False


async def fetch_all(
    sources: list[Source],
    delay: float = DELAY,
) -> int:
    """Fetch all eligible articles sequentially."""

    RAW.mkdir(parents=True, exist_ok=True)
    DATA.mkdir(parents=True, exist_ok=True)

    manifest = Manifest()

    headers = {
        "User-Agent": f"{USER_AGENT} ({CONTACT})",
    }

    timeout = httpx.Timeout(TIMEOUT)
    limits = httpx.Limits(
        max_connections=1,
        max_keepalive_connections=1,
    )

    async with httpx.AsyncClient(
        headers=headers,
        timeout=timeout,
        limits=limits,
        follow_redirects=True,
    ) as client:
        robots = Robots(client)
        gate = HostGate(delay)
        successful = 0

        for source in sources:
            try:
                result = await download_one(source, client, robots, gate, manifest)
                if result:
                    successful += 1
            except ValueError as exc:
                log.warning("Skipping %s: %s", source.title, exc)

    return successful


def main() -> None:
    """Run the PMC downloader."""
    import argparse

    parser = argparse.ArgumentParser(description="Fetch permitted GlucoLit PMC articles.")
    parser.add_argument(
        "--delay",
        type=float,
        default=DELAY,
        help="Seconds between requests to the same host.",
    )
    args = parser.parse_args()

    if args.delay < 1:
        parser.error("PMC request delay must be at least 1 second")

    sources = read_sources()
    successful = asyncio.run(fetch_all(sources, delay=args.delay))

    print(f"Downloaded or already present: {successful}/{len(sources)}")


if __name__ == "__main__":
    main()
