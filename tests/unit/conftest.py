import pytest
from fastapi.testclient import TestClient

from glucolit.api.deps import (
    get_gateway,
    get_repository,
    get_usage_repository,
)
from glucolit.api.main import create_app
from glucolit.config import Settings
from glucolit.llm.gateway import FakeLLM, LLMGateway

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


class FakeUsageRepo:
    async def by_day(self, days=7):
        return [
            {
                "day": "2026-11-25",
                "calls": 2,
                "errors": 0,
                "fallbacks": 1,
                "cost_inr": 0.0123,
            }
        ]


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
    app.dependency_overrides[get_gateway] = lambda: LLMGateway(
        [FakeLLM(script=["GlucoLit test answer"])]
    )
    app.dependency_overrides[get_usage_repository] = lambda: FakeUsageRepo()

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
