"""Tests for structured metadata extraction."""

import json

import pytest

from glucolit.llm.doc_meta import DocMeta
from glucolit.llm.extract import (
    MAX_ATTEMPTS,
    build_messages,
    extract_metadata,
    parse_metadata,
)
from glucolit.llm.gateway import FakeLLM, LLMGateway

PMCID = "PMC11937334"

VALID_METADATA = {
    "doc_kind": "research_article",
    "year": 2025,
    "language": "English",
    "summary": "A study examining diabetes management and glycemic control.",
    "topics": ["diabetes", "glycemic control"],
    "pmcid": PMCID,
    "journal": "Scientific Reports",
    "study_type": "Cross-sectional study",
    "population": "Adults with type 2 diabetes.",
    "sample_size": 18950,
}


def test_parse_valid_metadata():
    result = parse_metadata(json.dumps(VALID_METADATA))

    assert isinstance(result, DocMeta)
    assert result.pmcid == PMCID


def test_parse_invalid_json():
    with pytest.raises(ValueError, match="Invalid JSON"):
        parse_metadata("{invalid json}")


def test_parse_non_object():
    with pytest.raises(ValueError, match="JSON object"):
        parse_metadata('["not", "an", "object"]')


def test_parse_missing_required_field():
    data = VALID_METADATA.copy()
    del data["pmcid"]

    with pytest.raises(ValueError, match="pmcid"):
        parse_metadata(json.dumps(data))


def test_parse_forbids_extra_fields():
    data = VALID_METADATA | {"unknown": "value"}

    with pytest.raises(ValueError, match="Extra inputs"):
        parse_metadata(json.dumps(data))


def test_parse_invalid_pmcid():
    data = VALID_METADATA | {"pmcid": "not-a-pmcid"}

    with pytest.raises(ValueError, match="pmcid"):
        parse_metadata(json.dumps(data))


def test_build_messages_includes_known_pmcid():
    messages = build_messages(
        "Extract metadata.",
        "Sample article text",
        PMCID,
    )

    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert f"Known PMC identifier: {PMCID}" in messages[1]["content"]
    assert "<article>" in messages[1]["content"]
    assert "Sample article text" in messages[1]["content"]


@pytest.mark.asyncio
async def test_extract_retries_invalid_response():
    fake = FakeLLM(
        script=[
            "not json",
            json.dumps(VALID_METADATA),
        ]
    )
    gateway = LLMGateway([fake])

    metadata, result = await extract_metadata(
        gateway,
        "Extract metadata.",
        "extract_v1",
        "Sample article text",
        PMCID,
    )

    assert metadata.pmcid == PMCID
    assert result.provider == "fake"
    assert fake.calls == 2


@pytest.mark.asyncio
async def test_extract_stops_after_two_invalid_responses():
    fake = FakeLLM(script=["bad", "still bad", "unused"])
    gateway = LLMGateway([fake])

    with pytest.raises(ValueError, match="failed after 2 attempts"):
        await extract_metadata(
            gateway,
            "Extract metadata.",
            "extract_v1",
            "Sample article text",
            PMCID,
        )

    assert fake.calls == MAX_ATTEMPTS
    assert fake.calls == 2


@pytest.mark.asyncio
async def test_extract_rejects_empty_article():
    fake = FakeLLM()
    gateway = LLMGateway([fake])

    with pytest.raises(ValueError, match="cannot be empty"):
        await extract_metadata(
            gateway,
            "Extract metadata.",
            "extract_v1",
            "   ",
            PMCID,
        )

    assert fake.calls == 0


@pytest.mark.asyncio
async def test_extract_rejects_invalid_pmcid():
    fake = FakeLLM()
    gateway = LLMGateway([fake])

    with pytest.raises(ValueError, match="Invalid PMC identifier"):
        await extract_metadata(
            gateway,
            "Extract metadata.",
            "extract_v1",
            "Sample article text",
            "invalid-id",
        )

    assert fake.calls == 0


@pytest.mark.asyncio
async def test_extract_rejects_mismatched_pmcid():
    wrong_metadata = VALID_METADATA | {"pmcid": "PMC123456"}

    fake = FakeLLM(script=[json.dumps(wrong_metadata)] * MAX_ATTEMPTS)
    gateway = LLMGateway([fake])

    with pytest.raises(ValueError, match="does not match"):
        await extract_metadata(
            gateway,
            "Extract metadata.",
            "extract_v1",
            "Sample article text",
            PMCID,
        )

    assert fake.calls == MAX_ATTEMPTS
