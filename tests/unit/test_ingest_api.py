from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from glucolit.api.deps import get_session
from glucolit.api.main import create_app
from glucolit.api.routes import ingest
from glucolit.config import Settings


@pytest.fixture
def ingest_client(monkeypatch):
    settings = Settings(
        app_env="ci",
        database_url="postgresql://localhost:5432/unused",
        admin_token="test-admin-token",
        _env_file=None,
    )

    monkeypatch.setattr(ingest, "get_settings", lambda: settings)

    app = create_app(settings)

    async def fake_session():
        yield None

    app.dependency_overrides[get_session] = fake_session

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


def test_create_ingest_job_requires_admin_token(ingest_client):
    response = ingest_client.post("/v1/ingest")

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid admin token"


def test_create_ingest_job_rejects_invalid_token(ingest_client):
    response = ingest_client.post(
        "/v1/ingest",
        headers={"X-Admin-Token": "wrong-token"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid admin token"


def test_create_ingest_job_returns_503_without_admin_configuration(monkeypatch, ingest_client):
    settings = Settings(
        app_env="ci",
        database_url="postgresql://localhost:5432/unused",
        admin_token="",
        _env_file=None,
    )

    monkeypatch.setattr(ingest, "get_settings", lambda: settings)

    response = ingest_client.post(
        "/v1/ingest",
        headers={"X-Admin-Token": "test-admin-token"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Admin authentication is not configured"


def test_create_ingest_job_rejects_limit_above_maximum(ingest_client):
    response = ingest_client.post(
        "/v1/ingest?limit=11",
        headers={"X-Admin-Token": "test-admin-token"},
    )

    assert response.status_code == 422


def test_create_ingest_job_rejects_zero_limit(ingest_client):
    response = ingest_client.post(
        "/v1/ingest?limit=0",
        headers={"X-Admin-Token": "test-admin-token"},
    )

    assert response.status_code == 422


def test_create_ingest_job_handles_source_file_error(monkeypatch, ingest_client):
    def fail_read_sources():
        raise OSError("Source file unavailable")

    monkeypatch.setattr(ingest, "read_sources", fail_read_sources)

    response = ingest_client.post(
        "/v1/ingest",
        headers={"X-Admin-Token": "test-admin-token"},
    )

    assert response.status_code == 400
    assert "Could not read source list" in response.json()["detail"]


def test_create_ingest_job_handles_no_eligible_sources(monkeypatch, ingest_client):
    monkeypatch.setattr(ingest, "read_sources", lambda: [])

    response = ingest_client.post(
        "/v1/ingest",
        headers={"X-Admin-Token": "test-admin-token"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == ("No eligible sources are available for ingestion")


def test_create_ingest_job_success(monkeypatch, ingest_client):
    class FakeSession:
        def __init__(self):
            self.added = []

        def add(self, item):
            self.added.append(item)

        async def commit(self):
            pass

    fake_db = FakeSession()

    async def fake_session():
        yield fake_db

    ingest_client.app.dependency_overrides[get_session] = fake_session

    source = SimpleNamespace(
        url="https://example.org/PMC1234567",
        source="PMC",
        licence="CC BY 4.0",
        title="Test diabetes paper",
    )

    monkeypatch.setattr(ingest, "read_sources", lambda: [source])

    async def fake_enqueue(job_id):
        return "test-queue-job"

    monkeypatch.setattr(ingest, "enqueue_ingest", fake_enqueue)

    response = ingest_client.post(
        "/v1/ingest",
        headers={"X-Admin-Token": "test-admin-token"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["queue_job_id"] == "test-queue-job"
    assert data["requested"] == 1
    assert data["status"] == "queued"
    assert len(fake_db.added) == 2


def test_create_ingest_job_handles_redis_failure(monkeypatch, ingest_client):
    class FakeSession:
        def __init__(self):
            self.added = []
            self.deleted = []

        def add(self, item):
            self.added.append(item)

        async def commit(self):
            pass

        async def execute(self, statement):
            pass

        async def delete(self, item):
            self.deleted.append(item)

    fake_db = FakeSession()

    async def fake_session():
        yield fake_db

    ingest_client.app.dependency_overrides[get_session] = fake_session

    source = SimpleNamespace(
        url="https://example.org/PMC1234567",
        source="PMC",
        licence="CC BY 4.0",
        title="Test diabetes paper",
    )

    monkeypatch.setattr(ingest, "read_sources", lambda: [source])

    async def fail_enqueue(job_id):
        raise RuntimeError("Redis unavailable")

    monkeypatch.setattr(ingest, "enqueue_ingest", fail_enqueue)

    response = ingest_client.post(
        "/v1/ingest",
        headers={"X-Admin-Token": "test-admin-token"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == ("Could not submit ingestion job to Redis")
    assert len(fake_db.deleted) == 1


def test_get_ingest_job_status(monkeypatch, ingest_client):
    class FakeResult:
        def scalars(self):
            return self

        def all(self):
            return [
                SimpleNamespace(
                    id=1,
                    record={"source": "PMC", "title": "Test paper"},
                    status="done",
                    attempts=1,
                    pages=5,
                    error="",
                ),
                SimpleNamespace(
                    id=2,
                    record={"source": "PMC", "title": "Another paper"},
                    status="queued",
                    attempts=0,
                    pages=0,
                    error="",
                ),
            ]

    class FakeSession:
        async def get(self, model, job_id):
            return SimpleNamespace(id=job_id, requested=2)

        async def execute(self, statement):
            return FakeResult()

    async def fake_session():
        yield FakeSession()

    ingest_client.app.dependency_overrides[get_session] = fake_session

    response = ingest_client.get(
        "/v1/ingest/test-job-123",
        headers={"X-Admin-Token": "test-admin-token"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["job_id"] == "test-job-123"
    assert data["requested"] == 2
    assert data["status"] == "queued"
    assert data["counts"]["done"] == 1
    assert data["counts"]["queued"] == 1


def test_get_ingest_job_returns_404_when_missing(ingest_client):
    class FakeSession:
        async def get(self, model, job_id):
            return None

    async def fake_session():
        yield FakeSession()

    ingest_client.app.dependency_overrides[get_session] = fake_session

    response = ingest_client.get(
        "/v1/ingest/missing-job",
        headers={"X-Admin-Token": "test-admin-token"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Ingestion job not found"
