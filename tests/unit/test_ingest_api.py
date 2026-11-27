"""Tests for the protected background-ingestion API."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from glucolit.api.deps import get_session
from glucolit.api.main import create_app
from glucolit.api.routes import ingest as ingest_route
from glucolit.config import get_settings
from glucolit.db.models import IngestItem, IngestJob

ADMIN_TOKEN = "test-admin-token"


class FakeResult:
    """Minimal SQLAlchemy result substitute."""

    def __init__(self, items):
        self.items = items

    def scalars(self):
        return self

    def all(self):
        return self.items


class FakeSession:
    """Minimal async database session for route tests."""

    def __init__(self, job=None, items=None):
        self.job = job
        self.items = items or []
        self.added = []
        self.committed = False
        self.deleted = []

    async def get(self, model, object_id):
        if model is IngestJob and self.job and self.job.id == object_id:
            return self.job
        return None

    async def execute(self, statement):
        return FakeResult(self.items)

    def add(self, item):
        self.added.append(item)

    async def commit(self):
        self.committed = True

    async def delete(self, item):
        self.deleted.append(item)

    async def rollback(self):
        pass


@pytest.fixture
def app(monkeypatch):
    """Create an app with a configured test admin token."""
    monkeypatch.setattr(
        get_settings(),
        "admin_token",
        ADMIN_TOKEN,
    )
    return create_app()


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def headers():
    return {"X-Admin-Token": ADMIN_TOKEN}


@pytest.fixture
def fake_session():
    return FakeSession()


def override_session(app, session):
    async def get_fake_session():
        yield session

    app.dependency_overrides[get_session] = get_fake_session


def sample_source():
    return SimpleNamespace(
        url="https://pmc.ncbi.nlm.nih.gov/articles/PMC123456/",
        source="PMC",
        licence="CC BY 4.0",
        title="Example diabetes paper",
    )


def mock_sources(monkeypatch, sources):
    monkeypatch.setattr(
        ingest_route,
        "read_sources",
        lambda: sources,
    )
    monkeypatch.setattr(
        ingest_route,
        "enqueue_ingest",
        AsyncMock(return_value="queue-job-123"),
    )


def test_create_ingest_job_requires_admin_token(client):
    response = client.post(
        "/v1/ingest",
        json={"limit": 1},
    )

    assert response.status_code == 401


def test_create_ingest_job_rejects_limit_above_maximum(client, headers):
    response = client.post(
        "/v1/ingest",
        json={"limit": 2001},
        headers=headers,
    )

    assert response.status_code == 422


def test_create_ingest_job_handles_no_eligible_sources(
    app,
    client,
    headers,
    fake_session,
    monkeypatch,
):
    override_session(app, fake_session)
    monkeypatch.setattr(
        ingest_route,
        "read_sources",
        lambda: [],
    )

    response = client.post(
        "/v1/ingest",
        json={"limit": 10},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "no_work"
    assert response.json()["requested"] == 0


def test_create_ingest_job_success(
    app,
    client,
    headers,
    fake_session,
    monkeypatch,
):
    override_session(app, fake_session)
    mock_sources(monkeypatch, [sample_source()])

    response = client.post(
        "/v1/ingest",
        json={"limit": 1},
        headers=headers,
    )

    assert response.status_code == 202

    body = response.json()
    assert body["status"] == "queued"
    assert body["requested"] == 1
    assert body["queue_job_id"] == "queue-job-123"
    assert body["job_id"]

    assert fake_session.committed
    assert len(fake_session.added) == 2
    assert isinstance(fake_session.added[0], IngestJob)
    assert isinstance(fake_session.added[1], IngestItem)


def test_create_ingest_job_excludes_nc_nd_licences(
    app,
    client,
    headers,
    fake_session,
    monkeypatch,
):
    override_session(app, fake_session)

    allowed = sample_source()
    restricted = SimpleNamespace(
        url="https://example.com/restricted",
        source="PMC",
        licence="CC BY-NC-ND 4.0",
        title="Restricted paper",
    )

    mock_sources(monkeypatch, [allowed, restricted])

    response = client.post(
        "/v1/ingest",
        json={"limit": 10},
        headers=headers,
    )

    assert response.status_code == 202
    assert response.json()["requested"] == 1


def test_create_ingest_job_filters_by_source(
    app,
    client,
    headers,
    fake_session,
    monkeypatch,
):
    override_session(app, fake_session)

    sources = [
        sample_source(),
        SimpleNamespace(
            url="https://example.com/other",
            source="OTHER",
            licence="CC BY 4.0",
            title="Other paper",
        ),
    ]

    mock_sources(monkeypatch, sources)

    response = client.post(
        "/v1/ingest",
        json={"limit": 10, "source": "pmc"},
        headers=headers,
    )

    assert response.status_code == 202
    assert response.json()["requested"] == 1


def test_create_ingest_job_supports_query_parameters(
    app,
    client,
    headers,
    fake_session,
    monkeypatch,
):
    override_session(app, fake_session)
    mock_sources(monkeypatch, [sample_source()])

    response = client.post(
        "/v1/ingest?limit=1&source=PMC",
        headers=headers,
    )

    assert response.status_code == 202
    assert response.json()["requested"] == 1


def test_create_ingest_job_rejects_retry_without_original_job_id(
    app,
    client,
    headers,
    fake_session,
):
    override_session(app, fake_session)

    response = client.post(
        "/v1/ingest",
        json={"retry_failed": True},
        headers=headers,
    )

    assert response.status_code == 400
    assert "original job ID" in response.json()["detail"]


def test_create_ingest_job_handles_redis_failure(
    app,
    client,
    headers,
    fake_session,
    monkeypatch,
):
    override_session(app, fake_session)
    monkeypatch.setattr(
        ingest_route,
        "read_sources",
        lambda: [sample_source()],
    )
    monkeypatch.setattr(
        ingest_route,
        "enqueue_ingest",
        AsyncMock(side_effect=RuntimeError("Redis unavailable")),
    )

    response = client.post(
        "/v1/ingest",
        json={"limit": 1},
        headers=headers,
    )

    assert response.status_code == 503
    assert response.json()["detail"] == ("Could not submit ingestion job to Redis")


def test_get_ingest_job_not_found(
    app,
    client,
    headers,
    fake_session,
):
    override_session(app, fake_session)

    response = client.get(
        "/v1/ingest/missing-job",
        headers=headers,
    )

    assert response.status_code == 404


def test_get_ingest_job_returns_status_counts(
    app,
    client,
    headers,
):
    job = IngestJob(
        id="job-123",
        requested=3,
    )

    items = [
        IngestItem(
            id=1,
            job_id="job-123",
            record={"source": "PMC", "title": "Paper one"},
            status="done",
            attempts=1,
            pages=10,
        ),
        IngestItem(
            id=2,
            job_id="job-123",
            record={"source": "PMC", "title": "Paper two"},
            status="processing",
            attempts=1,
            pages=0,
        ),
        IngestItem(
            id=3,
            job_id="job-123",
            record={"source": "PMC", "title": "Paper three"},
            status="queued",
            attempts=0,
            pages=0,
        ),
    ]

    session = FakeSession(job=job, items=items)
    override_session(app, session)

    response = client.get(
        "/v1/ingest/job-123",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "processing"
    assert body["counts"] == {
        "queued": 1,
        "processing": 1,
        "done": 1,
        "failed": 0,
    }
    assert len(body["items"]) == 3


def test_get_dead_letter_items(
    app,
    client,
    headers,
):
    failed_item = IngestItem(
        id=7,
        job_id="job-123",
        record={
            "source": "PMC",
            "title": "Failed paper",
        },
        status="failed",
        attempts=3,
        error="Download failed",
        updated_at=datetime.now(UTC),
    )

    session = FakeSession(items=[failed_item])
    override_session(app, session)

    response = client.get(
        "/v1/ingest/dead-letter",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.json()
    assert body["count"] == 1
    assert body["items"][0]["title"] == "Failed paper"
    assert body["items"][0]["attempts"] == 3
    assert body["items"][0]["error"] == "Download failed"


def test_retry_failed_items_creates_new_job(
    app,
    client,
    headers,
    monkeypatch,
):
    original_job = IngestJob(
        id="job-original",
        requested=2,
    )

    failed_item = IngestItem(
        id=2,
        job_id="job-original",
        record={
            "url": "https://example.com/failed",
            "source": "PMC",
            "licence": "CC BY 4.0",
            "title": "Failed paper",
        },
        status="failed",
        attempts=3,
    )

    session = FakeSession(
        job=original_job,
        items=[failed_item],
    )
    override_session(app, session)

    monkeypatch.setattr(
        ingest_route,
        "enqueue_ingest",
        AsyncMock(return_value="queue-retry-123"),
    )

    response = client.post(
        "/v1/ingest/job-original/retry",
        headers=headers,
    )

    assert response.status_code == 202
    assert response.json()["requested"] == 1
    assert response.json()["status"] == "queued"
    assert response.json()["job_id"] != "job-original"


def test_retry_failed_items_returns_conflict_when_none_failed(
    app,
    client,
    headers,
):
    original_job = IngestJob(
        id="job-original",
        requested=1,
    )

    session = FakeSession(
        job=original_job,
        items=[],
    )
    override_session(app, session)

    response = client.post(
        "/v1/ingest/job-original/retry",
        headers=headers,
    )

    assert response.status_code == 409


def test_retry_failed_items_returns_404_for_missing_job(
    app,
    client,
    headers,
    fake_session,
):
    override_session(app, fake_session)

    response = client.post(
        "/v1/ingest/missing-job/retry",
        headers=headers,
    )

    assert response.status_code == 404
