"""Discover diabetes-related, licence-verified PMC open-access papers."""

import csv
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
CSV_FILE = ROOT / "data" / "sources.csv"

ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
OAI_URL = "https://pmc.ncbi.nlm.nih.gov/api/oai/v1/mh/"

HEADERS = {
    "User-Agent": (
        "GlucoLitResearchBot/1.0 (https://github.com/brithikaaids28-blip/prince28-hlt04-glucolit)"
    )
}

TARGET_NEW = 440
SEARCH_LIMIT = 3000

QUERY = (
    '("diabetes mellitus"[Title/Abstract] OR '
    '"type 2 diabetes"[Title/Abstract] OR '
    '"type 1 diabetes"[Title/Abstract] OR '
    '"diabetic complications"[Title/Abstract] OR '
    '"glycemic control"[Title/Abstract] OR '
    '"diabetic nephropathy"[Title/Abstract] OR '
    '"diabetic retinopathy"[Title/Abstract] OR '
    '"insulin resistance"[Title/Abstract] OR '
    '"diabetes treatment"[Title/Abstract]) '
    "AND open access[filter]"
)


def local_name(tag):
    return tag.split("}")[-1]


def get_existing():
    """Read existing PMC IDs from sources.csv."""
    existing = set()

    with CSV_FILE.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(
            line for line in file if line.strip() and not line.lstrip().startswith("#")
        )

        for row in reader:
            match = re.search(r"PMC\d+", row.get("url", ""), re.I)
            if match:
                existing.add(match.group().upper())

    return existing


def search_pmc(client):
    """Search PMC for diabetes-related open-access articles."""
    print("Searching PMC for diabetes-related open-access articles...")

    response = client.get(
        ESEARCH_URL,
        params={
            "db": "pmc",
            "term": QUERY,
            "retmax": SEARCH_LIMIT,
            "tool": "GlucoLit",
        },
    )
    response.raise_for_status()

    root = ET.fromstring(response.content)

    ids = [
        (element.text or "").strip()
        for element in root.iter()
        if local_name(element.tag) == "Id" and (element.text or "").strip()
    ]

    print("PMC search results:", len(ids))
    return ids


def get_license(article):
    """Extract a recognised Creative Commons licence."""

    for element in article.iter():
        if local_name(element.tag) != "license":
            continue

        href = ""

        for key, value in element.attrib.items():
            if local_name(key) == "href":
                href = value.lower()

        text = " ".join("".join(element.itertext()).split()).lower()
        combined = href + " " + text

        # Exclude NoDerivatives licences.
        if "nd" in href or "no derivatives" in text:
            return None

        match = re.search(
            r"creativecommons\.org/licenses/"
            r"(by-nc-sa|by-nc|by-sa|by)/(\d+\.\d+)",
            href,
        )

        if match:
            code, version = match.groups()

            labels = {
                "by": "CC BY",
                "by-sa": "CC BY-SA",
                "by-nc": "CC BY-NC",
                "by-nc-sa": "CC BY-NC-SA",
            }

            return f"{labels[code]} {version}"

        # Do not guess a licence from incomplete information.
        if "creative commons attribution" in combined and "noncommercial" not in combined:
            version_match = re.search(r"\b(\d+\.\d+)\b", combined)

            if version_match:
                return f"CC BY {version_match.group(1)}"

    return None


def get_article(client, numeric_id):
    """Retrieve one article and verify its licence."""

    pmcid = f"PMC{numeric_id}"

    response = client.get(
        OAI_URL,
        params={
            "verb": "GetRecord",
            "identifier": f"oai:pubmedcentral.nih.gov:{numeric_id}",
            "metadataPrefix": "pmc",
        },
    )
    response.raise_for_status()

    root = ET.fromstring(response.content)

    article = next(
        (element for element in root.iter() if local_name(element.tag) == "article"),
        None,
    )

    if article is None:
        return None

    licence = get_license(article)

    if not licence:
        return None

    title = ""

    title_element = next(
        (element for element in article.iter() if local_name(element.tag) == "article-title"),
        None,
    )

    if title_element is not None:
        title = " ".join("".join(title_element.itertext()).split())

    if not title:
        title = pmcid

    return {
        "url": f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/",
        "source": "pmc",
        "licence": licence,
        "title": title,
    }


def main():
    """Discover and save verified new articles."""

    existing = get_existing()
    print("Existing PMC papers:", len(existing))

    found = []
    seen = set(existing)

    with httpx.Client(
        headers=HEADERS,
        timeout=60,
        follow_redirects=True,
    ) as client:
        ids = search_pmc(client)

        for index, numeric_id in enumerate(ids, start=1):
            pmcid = f"PMC{numeric_id}"

            if pmcid in seen:
                continue

            try:
                record = get_article(client, numeric_id)

                if record:
                    found.append(record)
                    seen.add(pmcid)

                    print(f"Verified {len(found)}/{TARGET_NEW}: {pmcid} | {record['licence']}")

            except (
                httpx.HTTPError,
                ET.ParseError,
                ValueError,
            ) as exc:
                print(f"Skipped {pmcid}: {exc}")

            # One request per second; no concurrent requests.
            time.sleep(1)

            if len(found) >= TARGET_NEW:
                break

            if index % 100 == 0:
                print(f"Checked {index}/{len(ids)}; verified new papers: {len(found)}")

    if found:
        with CSV_FILE.open(
            "a",
            encoding="utf-8",
            newline="",
        ) as file:
            writer = csv.DictWriter(
                file,
                fieldnames=["url", "source", "licence", "title"],
            )
            writer.writerows(found)

    print("\nDiscovery completed.")
    print("New verified papers added:", len(found))
    print("Target:", TARGET_NEW)

    if len(found) < TARGET_NEW:
        print("Target not reached. Another search batch may be needed.")


if __name__ == "__main__":
    main()
