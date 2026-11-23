"""Unit tests for the GlucoLit downloader."""

import asyncio

import pytest

from glucolit.ingest import fetch


def write_csv(tmp_path, content):
    path = tmp_path / "sources.csv"
    path.write_text(content, encoding="utf-8")
    return path


# 1. Filename is generated consistently.
def test_filename_is_deterministic():
    url = "https://example.com/paper.pdf"
    assert fetch.filename_for(url) == fetch.filename_for(url)


# 2. Different URLs produce different filenames.
def test_different_urls_have_different_filenames():
    first = fetch.filename_for("https://example.com/one.pdf")
    second = fetch.filename_for("https://example.com/two.pdf")
    assert first != second


# 3. Read a valid source.
def test_read_valid_source(tmp_path):
    path = write_csv(
        tmp_path,
        "url,source,licence,title\nhttps://example.com/a.pdf,example,CC BY 4.0,Paper A\n",
    )

    sources = fetch.read_sources(path)

    assert len(sources) == 1
    assert sources[0].title == "Paper A"


# 4. Ignore comments and blank lines.
def test_read_sources_ignores_comments_and_blanks(tmp_path):
    path = write_csv(
        tmp_path,
        "# Research sources\n\n"
        "url,source,licence,title\n"
        "https://example.com/a.pdf,example,CC BY 4.0,Paper A\n",
    )

    assert len(fetch.read_sources(path)) == 1


# 5. Reject missing CSV columns.
def test_missing_columns_raises_error(tmp_path):
    path = write_csv(tmp_path, "url,title\nhttps://example.com/a.pdf,Paper A\n")

    with pytest.raises(ValueError):
        fetch.read_sources(path)


# 6. Reject a missing URL.
def test_missing_url_raises_error(tmp_path):
    path = write_csv(
        tmp_path,
        "url,source,licence,title\n,example,CC BY 4.0,Paper A\n",
    )

    with pytest.raises(ValueError, match="missing required field"):
        fetch.read_sources(path)


# 7. Reject a missing source name.
def test_missing_source_raises_error(tmp_path):
    path = write_csv(
        tmp_path,
        "url,source,licence,title\nhttps://example.com/a.pdf,,CC BY 4.0,Paper A\n",
    )

    with pytest.raises(ValueError, match="missing required field"):
        fetch.read_sources(path)


# 8. Reject a missing title.
def test_missing_title_raises_error(tmp_path):
    path = write_csv(
        tmp_path,
        "url,source,licence,title\nhttps://example.com/a.pdf,example,CC BY 4.0,\n",
    )

    with pytest.raises(ValueError, match="missing required field"):
        fetch.read_sources(path)


# 9. Reject a missing licence.
def test_missing_licence_raises_error(tmp_path):
    path = write_csv(
        tmp_path,
        "url,source,licence,title\nhttps://example.com/a.pdf,example,,Paper A\n",
    )

    with pytest.raises(ValueError, match="verified licence required"):
        fetch.read_sources(path)


# 10. Reject an unverified licence.
def test_review_required_licence_raises_error(tmp_path):
    path = write_csv(
        tmp_path,
        "url,source,licence,title\nhttps://example.com/a.pdf,example,REVIEW_REQUIRED,Paper A\n",
    )

    with pytest.raises(ValueError, match="verified licence required"):
        fetch.read_sources(path)


# 11. Reject non-HTTPS URLs.
def test_non_https_url_raises_error(tmp_path):
    path = write_csv(
        tmp_path,
        "url,source,licence,title\nhttp://example.com/a.pdf,example,CC BY 4.0,Paper A\n",
    )

    with pytest.raises(ValueError, match="HTTPS URL required"):
        fetch.read_sources(path)


# 12. Empty manifest starts with no entries.
def test_manifest_starts_empty(tmp_path):
    manifest = fetch.Manifest(tmp_path / "manifest.jsonl")
    assert manifest.entries == {}


# 13. Manifest entry can be saved and loaded.
def test_manifest_add_and_reload(tmp_path):
    path = tmp_path / "manifest.jsonl"
    manifest = fetch.Manifest(path)

    entry = fetch.ManifestEntry(
        url="https://example.com/a.pdf",
        title="Paper A",
        source="example",
        licence="CC BY 4.0",
        filename="paper.pdf",
        sha256="abc123",
        bytes=100,
        downloaded_at="2026-11-23T00:00:00Z",
        status="downloaded",
    )

    manifest.add(entry)

    loaded = fetch.Manifest(path)
    assert "https://example.com/a.pdf" in loaded.entries


# 14. Manifest recognises an existing valid file.
def test_manifest_contains_valid_file(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch, "RAW", tmp_path)

    paper = tmp_path / "paper.pdf"
    paper.write_bytes(b"paper content")

    manifest = fetch.Manifest(tmp_path / "manifest.jsonl")
    manifest.add(
        fetch.ManifestEntry(
            url="https://example.com/a.pdf",
            title="Paper A",
            source="example",
            licence="CC BY 4.0",
            filename="paper.pdf",
            sha256="abc",
            bytes=len(b"paper content"),
            downloaded_at="2026-11-23T00:00:00Z",
            status="downloaded",
        )
    )

    assert manifest.contains("https://example.com/a.pdf")


# 15. Manifest rejects a missing file.
def test_manifest_missing_file_returns_false(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch, "RAW", tmp_path)

    manifest = fetch.Manifest(tmp_path / "manifest.jsonl")
    manifest.entries["https://example.com/a.pdf"] = {
        "filename": "missing.pdf",
        "bytes": 100,
        "status": "downloaded",
    }

    assert not manifest.contains("https://example.com/a.pdf")


# 16. Manifest rejects a file with the wrong size.
def test_manifest_wrong_size_returns_false(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch, "RAW", tmp_path)

    (tmp_path / "paper.pdf").write_bytes(b"short")

    manifest = fetch.Manifest(tmp_path / "manifest.jsonl")
    manifest.entries["https://example.com/a.pdf"] = {
        "filename": "paper.pdf",
        "bytes": 100,
        "status": "downloaded",
    }

    assert not manifest.contains("https://example.com/a.pdf")


# 17. Manifest rejects an unsuccessful download status.
def test_manifest_wrong_status_returns_false(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch, "RAW", tmp_path)

    (tmp_path / "paper.pdf").write_bytes(b"paper")

    manifest = fetch.Manifest(tmp_path / "manifest.jsonl")
    manifest.entries["https://example.com/a.pdf"] = {
        "filename": "paper.pdf",
        "bytes": 5,
        "status": "failed",
    }

    assert not manifest.contains("https://example.com/a.pdf")


class FakeResponse:
    def __init__(self, status_code, text=""):
        self.status_code = status_code
        self.text = text


class FakeClient:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = 0

    async def get(self, url):
        self.calls += 1

        if self.error:
            raise self.error

        return self.response


# 18. Robots.txt can allow a permitted URL.
def test_robots_allows_permitted_url():
    client = FakeClient(
        FakeResponse(
            200,
            "User-agent: *\nAllow: /\n",
        )
    )

    robots = fetch.Robots(client)

    result = asyncio.run(robots.allowed("https://example.com/paper.pdf"))

    assert result is True


# 19. Robots.txt failures block downloads.
def test_robots_failure_blocks_url():
    client = FakeClient(FakeResponse(403, "Forbidden"))
    robots = fetch.Robots(client)

    result = asyncio.run(robots.allowed("https://example.com/paper.pdf"))

    assert result is False


# 20. PMC filenames use XML extension.
def test_filename_uses_xml_extension():
    filename = fetch.filename_for("https://pmc.ncbi.nlm.nih.gov/articles/PMC11078398/")
    assert filename.endswith(".xml")


# 21. Extract a PMCID from an article URL.
def test_get_pmcid():
    url = "https://pmc.ncbi.nlm.nih.gov/articles/PMC11078398/"
    assert fetch.get_pmcid(url) == "PMC11078398"


# 22. Reject URLs without a PMCID.
def test_get_pmcid_invalid_url():
    with pytest.raises(ValueError, match="Could not find a PMCID"):
        fetch.get_pmcid("https://example.com/article")


# 23. Recognise valid article XML.
def test_has_article():
    xml = b"<article><body>Test paper</body></article>"
    assert fetch.has_article(xml) is True


# 24. Reject XML without an article.
def test_has_article_rejects_invalid_content():
    xml = b"<OAI-PMH><error>Not found</error></OAI-PMH>"
    assert fetch.has_article(xml) is False


# 25. Skip NoDerivatives articles without requesting them.
def test_download_skips_no_derivatives_article(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch, "RAW", tmp_path)

    source = fetch.Source(
        url="https://pmc.ncbi.nlm.nih.gov/articles/PMC12345678/",
        source="pmc",
        licence="CC BY-NC-ND 4.0",
        title="Test paper",
    )

    client = FakeClient()
    robots = fetch.Robots(client)
    gate = fetch.HostGate(1)
    manifest = fetch.Manifest(tmp_path / "manifest.jsonl")

    result = asyncio.run(fetch.download_one(source, client, robots, gate, manifest))

    assert result is False
    assert client.calls == 0
