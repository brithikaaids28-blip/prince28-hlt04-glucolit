import pytest
from fastapi.testclient import TestClient

from glucolit.api.deps import get_repository
from glucolit.api.main import create_app
from glucolit.config import Settings

SAMPLE = [
    {"id": "001", "title": "Alpha guideline", "year": 2023},
    {"id": "002", "title": "Beta circular", "year": 2024},
    {"id": "003", "title": "Gamma notice", "year": 2025},
]


class FakeRepo:
    def __init__(self, rows):
        self.rows = rows

    async def list(self, *, q, filters, limit, offset):
        rows = [
            r
            for r in self.rows
            if (not q or q.lower() in str(r).lower())
            and all(str(r.get(k)) == v for k, v in filters.items())
        ]
        return len(rows), rows[offset : offset + limit]

    async def get(self, external_id):
        return next(
            (r for r in self.rows if r["id"] == external_id),
            None,
        )


@pytest.fixture
def settings():
    return Settings(
        app_env="ci",
        database_url="postgresql://localhost:5432/unused",
        _env_file=None,
    )


@pytest.fixture
def client(settings):
    app = create_app(settings)
    app.dependency_overrides[get_repository] = lambda: FakeRepo(SAMPLE)

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
