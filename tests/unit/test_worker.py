from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from arq import Retry

from glucolit.ingest import worker
from glucolit.ingest.worker import (
    FIRST_PAGES,
    MAX_ARTICLE_CHARS,
    RETRY_DELAY_SECONDS,
    WorkerSettings,
    article_text,
    process_ingest_job,
    save_metadata,
)


def test_article_text_uses_only_first_two_pages():
    document = SimpleNamespace(
        pages=[
            SimpleNamespace(page_no=3, text="Third page"),
            SimpleNamespace(page_no=1, text=" First page "),
            SimpleNamespace(page_no=2, text=" Second page "),
        ]
    )

    result = article_text(document)

    assert result == "First page\n\nSecond page"


def test_article_text_ignores_empty_pages():
    document = SimpleNamespace(
        pages=[
            SimpleNamespace(page_no=1, text=""),
            SimpleNamespace(page_no=2, text=" Useful content "),
            SimpleNamespace(page_no=3, text="Not included"),
        ]
    )

    assert article_text(document) == "Useful content"


def test_article_text_respects_character_limit():
    document = SimpleNamespace(
        pages=[
            SimpleNamespace(page_no=1, text="A" * (MAX_ARTICLE_CHARS + 100)),
        ]
    )

    result = article_text(document)

    assert len(result) == MAX_ARTICLE_CHARS


def test_article_text_uses_configured_page_limit():
    assert FIRST_PAGES == 2


def test_save_metadata_preserves_existing_metadata():
    document = SimpleNamespace(
        metadata_={
            "parser": "jats",
            "year": 2025,
        }
    )

    save_metadata(
        document,
        {"journal": "Test Journal", "study_type": "RCT"},
        "extract_v1",
    )

    assert document.metadata_["parser"] == "jats"
    assert document.metadata_["year"] == 2025
    assert document.metadata_["journal"] == "Test Journal"
    assert document.metadata_["study_type"] == "RCT"
    assert document.metadata_["extraction_status"] == "success"
    assert document.metadata_["extraction_prompt_version"] == "extract_v1"


def test_save_metadata_handles_empty_existing_metadata():
    document = SimpleNamespace(metadata_=None)

    save_metadata(document, {"year": 2026}, "extract_v1")

    assert document.metadata_["year"] == 2026
    assert document.metadata_["extraction_status"] == "success"


def test_worker_settings_registers_ingest_job():
    assert process_ingest_job in WorkerSettings.functions
    assert WorkerSettings.max_jobs == 1
    assert WorkerSettings.job_timeout > 0
    assert WorkerSettings.max_tries > 0


def test_retry_delay_is_30_seconds():
    assert RETRY_DELAY_SECONDS == 30


def test_arq_retry_uses_configured_delay():
    retry = Retry(defer=RETRY_DELAY_SECONDS)

    assert isinstance(retry, RuntimeError)
    assert retry.defer_score == RETRY_DELAY_SECONDS * 1000


@pytest.mark.asyncio
async def test_worker_retries_after_temporary_download_failure(tmp_path, monkeypatch):
    item = SimpleNamespace(
        id=1,
        record={
            "url": "https://example.com/paper.xml",
            "source": "test",
            "licence": "CC BY 4.0",
            "title": "Test paper",
        },
        status="pending",
        attempts=0,
        error="",
    )

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, model, item_id):
            return item

        async def commit(self):
            return None

    monkeypatch.setattr(
        worker,
        "AsyncSessionLocal",
        lambda: FakeSession(),
    )
    monkeypatch.setattr(worker, "RAW", tmp_path / "raw")
    monkeypatch.setattr(
        worker,
        "MANIFEST",
        tmp_path / "manifest.jsonl",
    )

    download_mock = AsyncMock(side_effect=RuntimeError("temporary download error"))
    monkeypatch.setattr(worker, "download_one", download_mock)

    ctx = {
        "manifest": object(),
        "http_client": object(),
        "robots": object(),
        "host_gate": object(),
    }

    with pytest.raises(Retry):
        await worker.process_ingest_item(ctx, 1)

    assert download_mock.await_count == 1
    assert item.status == "failed"
    assert item.attempts == 1
    assert "temporary download error" in item.error


@pytest.mark.asyncio
async def test_worker_reprocesses_interrupted_processing_item(monkeypatch):
    interrupted_item = SimpleNamespace(
        id=42,
        status="processing",
    )

    class FakeResult:
        def scalars(self):
            return self

        def all(self):
            return [interrupted_item]

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def execute(self, statement):
            sql = str(statement)
            assert "status" in sql
            assert "done" in statement.compile().params.values()
            return FakeResult()

    process_mock = AsyncMock()
    monkeypatch.setattr(
        worker,
        "AsyncSessionLocal",
        lambda: FakeSession(),
    )
    monkeypatch.setattr(worker, "process_ingest_item", process_mock)

    await process_ingest_job({}, "test-job")

    process_mock.assert_awaited_once_with({}, 42)
