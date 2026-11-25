"""Compare the GlucoLit JATS parser with Trafilatura on 10 large XML files."""

import csv
import json
import re
import time
from pathlib import Path

import trafilatura

from glucolit.ingest.parse import parse_jats_xml

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data" / "manifest.jsonl"
RAW_DIR = ROOT / "data" / "raw"
OUTPUT = ROOT / "data" / "parser_comparison.csv"
LIMIT = 10


def word_count(text):
    return len(re.findall(r"\b\w+\b", text))


def main():
    records = []

    with MANIFEST.open(encoding="utf-8") as file:
        for line in file:
            if line.strip():
                record = json.loads(line)
                path = RAW_DIR / record["filename"]

                if path.exists():
                    records.append((path.stat().st_size, record, path))

    hardest = sorted(records, key=lambda item: item[0], reverse=True)[:LIMIT]

    results = []

    for index, (size, record, path) in enumerate(hardest, start=1):
        print(f"\n[{index}/{len(hardest)}] {record['title']}")

        result = {
            "title": record["title"],
            "filename": path.name,
            "bytes": size,
        }

        try:
            start = time.perf_counter()
            jats = parse_jats_xml(path)
            jats_time = time.perf_counter() - start

            jats_text = "\n".join(page.text for page in jats.pages)

            result.update(
                {
                    "jats_words": word_count(jats_text),
                    "jats_pages": len(jats.pages),
                    "jats_headings": len(re.findall(r"(?m)^#{1,6}\s+", jats_text)),
                    "jats_seconds": round(jats_time, 4),
                    "jats_error": "",
                }
            )

        except Exception as exc:
            result.update(
                {
                    "jats_words": 0,
                    "jats_pages": 0,
                    "jats_headings": 0,
                    "jats_seconds": 0,
                    "jats_error": str(exc)[:200],
                }
            )

        try:
            xml_text = path.read_text(encoding="utf-8", errors="replace")

            start = time.perf_counter()
            markdown = trafilatura.extract(
                xml_text,
                output_format="markdown",
                include_tables=True,
            )
            traf_time = time.perf_counter() - start

            markdown = markdown or ""

            result.update(
                {
                    "trafilatura_words": word_count(markdown),
                    "trafilatura_headings": len(re.findall(r"(?m)^#{1,6}\s+", markdown)),
                    "trafilatura_tables": markdown.count("|"),
                    "trafilatura_seconds": round(traf_time, 4),
                    "trafilatura_error": "" if markdown else "No text extracted",
                }
            )

        except Exception as exc:
            result.update(
                {
                    "trafilatura_words": 0,
                    "trafilatura_headings": 0,
                    "trafilatura_tables": 0,
                    "trafilatura_seconds": 0,
                    "trafilatura_error": str(exc)[:200],
                }
            )

        results.append(result)

        print(
            f"JATS: {result['jats_words']} words | Trafilatura: {result['trafilatura_words']} words"
        )

    if not results:
        raise RuntimeError("No XML files were available for comparison.")

    with OUTPUT.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows(results)

    print("\nComparison completed.")
    print("Articles compared:", len(results))
    print("Results saved to:", OUTPUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
