"""Measure the GlucoLit corpus and generate dataset and capacity reports."""

from __future__ import annotations

import argparse
import json
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data" / "manifest.jsonl"
RAW = ROOT / "data" / "raw"
DATASET = ROOT / "DATASET.md"
CAPACITY = ROOT / "docs" / "CAPACITY.md"

WORDS_PER_PAGE = 500
TOKENS_PER_WORD = 1.3
BYTES_PER_VECTOR_VALUE = 4


def number(value: float | int) -> str:
    """Format a number with thousands separators."""
    return f"{value:,.0f}"


def read_corpus() -> list[dict]:
    """Read downloaded manifest entries and measure their XML body text."""
    if not MANIFEST.exists():
        raise FileNotFoundError(f"Manifest not found: {MANIFEST}")

    papers = []

    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue

        entry = json.loads(line)

        if entry.get("status") != "downloaded":
            continue

        filename = entry.get("filename", "")
        path = RAW / filename

        if not filename or not path.is_file():
            continue

        root = ET.parse(path).getroot()
        body_text = []

        for element in root.iter():
            if element.tag.split("}")[-1] == "body":
                body_text.extend(element.itertext())

        text = " ".join(body_text).strip()

        words = len(re.findall(r"\b[\w]+(?:['ΓÇÖ-][\w]+)*\b", text))
        tokens = math.ceil(words * TOKENS_PER_WORD)
        pages = math.ceil(words / WORDS_PER_PAGE) if words else 0

        papers.append(
            {
                "filename": filename,
                "title": entry.get("title", "Unknown"),
                "licence": entry.get("licence", "Unknown"),
                "words": words,
                "tokens": tokens,
                "pages": pages,
                "bytes": path.stat().st_size,
            }
        )

    if not papers:
        raise ValueError("No downloaded XML papers with manifest entries were found.")

    return papers


def replace_generated(path: Path, heading: str, content: str) -> None:
    """Replace the generated section while preserving manual notes."""
    path.parent.mkdir(parents=True, exist_ok=True)

    if not path.exists():
        path.write_text(
            f"{heading}\n\n<!-- generated:start -->\n<!-- generated:end -->\n",
            encoding="utf-8",
        )

    original = path.read_text(encoding="utf-8")

    start = "<!-- generated:start -->"
    end = "<!-- generated:end -->"

    if start not in original or end not in original:
        original = original.rstrip() + f"\n\n{start}\n{end}\n"

    before, remainder = original.split(start, 1)
    _, after = remainder.split(end, 1)

    updated = f"{before}{start}\n{content.rstrip()}\n{end}{after}"
    path.write_text(updated, encoding="utf-8")


def main() -> None:
    """Generate dataset and capacity reports."""
    parser = argparse.ArgumentParser(
        description="Measure GlucoLit papers and generate capacity reports."
    )

    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--full-files", type=int)
    target.add_argument("--full-pages", type=int)

    parser.add_argument("--embed-usd", type=float, default=0.20)
    parser.add_argument("--dims", type=int, default=1024)
    parser.add_argument("--chunk-tokens", type=int, default=500)
    parser.add_argument("--usd-inr", type=float, default=95)

    args = parser.parse_args()

    if (
        (args.full_files is not None and args.full_files <= 0)
        or (args.full_pages is not None and args.full_pages <= 0)
        or args.embed_usd < 0
        or args.dims <= 0
        or args.chunk_tokens <= 0
        or args.usd_inr <= 0
    ):
        parser.error("Targets and dimensions must be positive; price cannot be negative.")

    papers = read_corpus()

    files = len(papers)
    pages = sum(paper["pages"] for paper in papers)
    words = sum(paper["words"] for paper in papers)
    tokens = sum(paper["tokens"] for paper in papers)
    raw_bytes = sum(paper["bytes"] for paper in papers)

    if pages == 0 or tokens == 0:
        raise ValueError("The downloaded papers contain no measurable body text.")

    tokens_per_page = tokens / pages
    tokens_per_paper = tokens / files

    if args.full_files is not None:
        target_files = args.full_files
        target_pages = math.ceil(target_files * pages / files)
        target_tokens = math.ceil(target_files * tokens_per_paper)
    else:
        target_pages = args.full_pages
        target_files = math.ceil(target_pages * files / pages)
        target_tokens = math.ceil(target_pages * tokens_per_page)

    chunks = math.ceil(target_tokens / args.chunk_tokens)
    current_chunks = math.ceil(tokens / args.chunk_tokens)

    embedding_inr = target_tokens / 1_000_000 * args.embed_usd * args.usd_inr
    current_embedding_inr = tokens / 1_000_000 * args.embed_usd * args.usd_inr

    vector_mib = chunks * args.dims * BYTES_PER_VECTOR_VALUE / (1024**2)
    current_vector_mib = current_chunks * args.dims * BYTES_PER_VECTOR_VALUE / (1024**2)

    raw_mib = raw_bytes / (1024**2)

    dataset_content = "\n".join(
        [
            "| Measurement | Current corpus |",
            "|---|---:|",
            f"| Downloaded XML papers | {number(files)} |",
            f"| Estimated pages | {number(pages)} |",
            f"| Body words | {number(words)} |",
            f"| Estimated tokens | {number(tokens)} |",
            f"| Raw XML size | {raw_mib:.2f} MiB |",
            f"| Average tokens per paper | {number(tokens_per_paper)} |",
            f"| Average tokens per page | {number(tokens_per_page)} |",
            "",
            "## Paper Licences",
            "",
            "| Paper | Licence |",
            "|---|---|",
            *[f"| {paper['title'].replace('|', '/')} | {paper['licence']} |" for paper in papers],
            "",
            "**Measurement method:** Text is extracted from each XML `body` element.",
            (
                f"Pages are estimated at {WORDS_PER_PAGE} words per page. "
                f"Tokens are estimated at {TOKENS_PER_WORD} tokens per word."
            ),
            "These are planning estimates, not PDF page counts or tokenizer measurements.",
        ]
    )

    capacity_content = "\n".join(
        [
            "| Measurement | Current corpus | Full target |",
            "|---|---:|---:|",
            f"| Papers | {number(files)} | {number(target_files)} |",
            f"| Estimated pages | {number(pages)} | {number(target_pages)} |",
            f"| Estimated tokens | {number(tokens)} | {number(target_tokens)} |",
            f"| Tokens per page | {number(tokens_per_page)} | {number(tokens_per_page)} |",
            (
                f"| Chunks ({args.chunk_tokens} tokens each) | "
                f"{number(current_chunks)} | {number(chunks)} |"
            ),
            (f"| Embedding cost | Rs {current_embedding_inr:.2f} | Rs {embedding_inr:.2f} |"),
            (
                f"| Vector storage ({args.dims} dimensions, float32) | "
                f"{current_vector_mib:.2f} MiB | {vector_mib:.2f} MiB |"
            ),
            "",
            (
                f"**Assumptions:** {args.embed_usd:.2f} USD per million "
                f"tokens, Rs {args.usd_inr:.2f} per USD."
            ),
            (
                f"{args.dims} embedding dimensions, {args.chunk_tokens} "
                "tokens per chunk, and 4 bytes per vector value."
            ),
            "Storage excludes PostgreSQL indexes, metadata, and text.",
            "",
            "**Measurement note:** Token counts and pages are estimates based on XML body text.",
            "They are not actual embedding tokenizer measurements or PDF page counts.",
        ]
    )

    replace_generated(
        DATASET,
        "# Dataset: GlucoLit",
        dataset_content,
    )

    replace_generated(
        CAPACITY,
        "# Capacity plan: GlucoLit",
        capacity_content,
    )

    print(f"files={files} estimated_pages={pages} -> wrote DATASET.md and docs/CAPACITY.md")


if __name__ == "__main__":
    main()
