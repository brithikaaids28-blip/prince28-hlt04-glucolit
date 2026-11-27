from types import SimpleNamespace

from glucolit.ingest.worker import (
    FIRST_PAGES,
    MAX_ARTICLE_CHARS,
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
