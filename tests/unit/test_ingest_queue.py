"""Tests for Redis ingestion queue helpers."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from glucolit.ingest import queue


def test_enqueue_ingest_uses_deterministic_job_id(monkeypatch):
    """The database job ID should determine the ARQ job ID."""
    redis = AsyncMock()
    redis.enqueue_job.return_value = None
    monkeypatch.setattr(
        queue,
        "get_queue",
        AsyncMock(return_value=redis),
    )

    result = asyncio.run(queue.enqueue_ingest("database-job-123"))

    assert result == "glucolit-ingest-database-job-123"
    redis.enqueue_job.assert_awaited_once_with(
        "process_ingest_job",
        "database-job-123",
        _job_id="glucolit-ingest-database-job-123",
    )
    redis.aclose.assert_awaited_once()


def test_enqueue_ingest_closes_redis_when_submission_fails(monkeypatch):
    """Redis must close even when queue submission raises an error."""
    redis = AsyncMock()
    redis.enqueue_job.side_effect = RuntimeError("Redis unavailable")
    monkeypatch.setattr(
        queue,
        "get_queue",
        AsyncMock(return_value=redis),
    )

    with pytest.raises(RuntimeError, match="Redis unavailable"):
        asyncio.run(queue.enqueue_ingest("database-job-456"))

    redis.aclose.assert_awaited_once()
