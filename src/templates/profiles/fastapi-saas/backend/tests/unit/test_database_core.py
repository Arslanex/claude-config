"""infra/database: ayar, motor, yonlendirici, RLS komutlari, model karisimlari (ARCH-0003, ARCH-0004)."""

import pytest
from sqlalchemy import inspect

from PKG_NAME.config import DatabaseSettings, DeploymentSettings
from PKG_NAME.infra.database import TenantRouter, create_engine, create_session_factory
from PKG_NAME.infra.database.models import Base, IdMixin, TenantMixin, TimestampMixin
from PKG_NAME.infra.database.rls import drop_tenant_rls_statements, tenant_rls_statements

URL = "postgresql+asyncpg://u:secret@localhost:5432/db"


def settings(monkeypatch, **env):
    monkeypatch.setenv("DATABASE_URL", URL)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return DatabaseSettings()  # type: ignore[call-arg]


def test_settings_hide_the_url_and_read_pool_limits(monkeypatch):
    loaded = settings(monkeypatch, DB_POOL_SIZE="7")
    assert "secret" not in repr(loaded)
    assert loaded.db_pool_size == 7


async def test_engine_uses_the_pool_limits_and_statement_timeout(monkeypatch):
    engine = create_engine(settings(monkeypatch, DB_POOL_SIZE="3", DB_STATEMENT_TIMEOUT_MS="2000"))
    try:
        assert engine.pool.size() == 3
        assert engine.sync_engine.hide_parameters is True
        assert engine.url.password == "secret"
        assert create_session_factory(engine).kw["expire_on_commit"] is False
    finally:
        await engine.dispose()


def test_router_returns_the_shared_factory_and_rejects_db_per_tenant():
    shared = object()
    assert TenantRouter(DeploymentSettings(), shared).sessions() is shared  # type: ignore[arg-type]
    with pytest.raises(NotImplementedError):
        TenantRouter(DeploymentSettings(tenancy="db_per_tenant"), shared)  # type: ignore[arg-type]


def test_rls_statements_enable_force_and_drop():
    up = tenant_rls_statements("notes")
    assert up[0] == "ALTER TABLE notes ENABLE ROW LEVEL SECURITY"
    assert up[1] == "ALTER TABLE notes FORCE ROW LEVEL SECURITY"
    assert "USING (tenant_id = " in up[2] and "WITH CHECK (tenant_id = " in up[2]
    assert drop_tenant_rls_statements("notes")[0] == "DROP POLICY IF EXISTS tenant_isolation ON notes"


@pytest.mark.parametrize("build", [tenant_rls_statements, drop_tenant_rls_statements])
def test_rls_statements_reject_unsafe_table_names(build):
    with pytest.raises(ValueError):
        build("notes; drop table users")


def test_mixins_give_id_timestamps_and_tenant():
    class Probe(IdMixin, TimestampMixin, TenantMixin, Base):
        __tablename__ = "mixin_probe"

    try:
        columns = {column.name: column for column in inspect(Probe).columns}
        assert set(columns) == {"id", "created_at", "updated_at", "tenant_id"}
        assert columns["id"].primary_key
        assert columns["tenant_id"].index
        assert columns["created_at"].type.timezone
        assert columns["id"].default.arg(None).version == 7
    finally:
        Base.metadata.remove(Probe.__table__)
