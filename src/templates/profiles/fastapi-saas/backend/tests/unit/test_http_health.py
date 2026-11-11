"""Saglik ve hazir olma uclari, uygulama acilisi, API sozlesmesi (ARCH-0002, ARCH-0007)."""

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import ProgrammingError

from PKG_NAME.infra.database import UnitOfWork
from PKG_NAME.interface.cli.openapi import render
from PKG_NAME.interface.http.app import create_app
from PKG_NAME.interface.http.deps import UnitOfWorkDep, code_heads, readiness

from tests.support.fakes import FakeEngine, FakeSession, FakeSessions


def test_health_answers_ok_without_a_database():
    response = TestClient(create_app()).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_lifespan_builds_the_pool_and_disposes_it(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/db")
    app = create_app()
    with TestClient(app):
        assert app.state.migration_heads == code_heads()
        assert app.state.sessions.kw["expire_on_commit"] is False
    assert app.state.engine.pool.checkedout() == 0


def ready_client(engine: FakeEngine, heads: set[str]) -> TestClient:
    app = create_app()
    app.state.engine = engine
    app.state.migration_heads = heads
    return TestClient(app)


def test_ready_is_200_when_schema_matches_the_code():
    response = ready_client(FakeEngine(rows=[("abc",)]), {"abc"}).get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {"database": "ok", "schema": "ok"}}


def test_ready_is_503_when_schema_is_behind():
    response = ready_client(FakeEngine(rows=[("old",)]), {"new"}).get("/ready")
    assert response.status_code == 503
    assert response.json()["checks"] == {"database": "ok", "schema": "behind"}


async def test_readiness_reports_an_unreachable_database_without_details():
    checks = await readiness(FakeEngine(error=OSError("password=x")), {"abc"})  # type: ignore[arg-type]
    assert checks == {"database": "unreachable", "schema": "skipped"}


async def test_readiness_reports_a_missing_migration_table_as_behind():
    missing = ProgrammingError("select", {}, Exception("relation alembic_version does not exist"))
    assert await readiness(FakeEngine(error=missing), {"abc"}) == {"database": "ok", "schema": "behind"}  # type: ignore[arg-type]
    assert await readiness(FakeEngine(error=missing), set()) == {"database": "ok", "schema": "ok"}  # type: ignore[arg-type]


def test_code_heads_is_empty_before_the_first_migration():
    assert code_heads() == set()


def test_unit_of_work_dependency_commits_before_the_response():
    fake = FakeSession()
    app = FastAPI()
    app.state.sessions = FakeSessions(fake)

    @app.post("/touch")
    async def touch(uow: UnitOfWorkDep) -> dict[str, bool]:
        assert isinstance(uow, UnitOfWork)
        await uow.session()
        return {"ok": True}

    assert TestClient(app).post("/touch").status_code == 200
    assert fake.names() == ["commit", "close"]


def test_contract_is_deterministic_and_lists_the_health_routes():
    first = render()
    assert first == render()
    assert first.endswith("\n")
    paths = json.loads(first)["paths"]
    assert "/health" in paths and "/ready" in paths
