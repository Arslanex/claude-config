"""
Is birimi ve RLS gercek Postgres'te (ARCH-0003, ARCH-0004).

Tablo sahibi olmayan, RLS'i asamayan bir rol kurulur; uygulama o rolle baglanir. Her test kendi tablosunu kurar ve
siler.
"""

from collections.abc import AsyncIterator
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from PKG_NAME.core import new_id
from PKG_NAME.infra.database import UnitOfWork, create_session_factory
from PKG_NAME.infra.database.rls import tenant_rls_statements

ROLE = "rls_probe_app"
TABLE = "rls_probe"
TENANT_A = UUID("01900000-0000-7000-8000-00000000000a")
TENANT_B = UUID("01900000-0000-7000-8000-00000000000b")


@pytest.fixture
async def sessions(database_url: str) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    owner = create_async_engine(database_url)
    async with owner.begin() as connection:
        await connection.execute(text(f"drop table if exists {TABLE}"))
        await connection.execute(text(f"drop role if exists {ROLE}"))
        await connection.execute(text(f"create role {ROLE} login password '{ROLE}' nosuperuser nobypassrls"))
        await connection.execute(
            text(f"create table {TABLE} (id uuid primary key, tenant_id uuid not null, title text)")
        )
        for statement in tenant_rls_statements(TABLE):
            await connection.execute(text(statement))
        await connection.execute(text(f"grant select, insert, update, delete on {TABLE} to {ROLE}"))
    app: AsyncEngine = create_async_engine(make_url(database_url).set(username=ROLE, password=ROLE))
    try:
        yield create_session_factory(app)
    finally:
        await app.dispose()
        async with owner.begin() as connection:
            await connection.execute(text(f"drop table if exists {TABLE}"))
            await connection.execute(text(f"drop role if exists {ROLE}"))
        await owner.dispose()


async def insert(uow: UnitOfWork, tenant: UUID, title: str) -> None:
    session = await uow.session()
    await session.execute(
        text(f"insert into {TABLE} (id, tenant_id, title) values (:id, :tenant, :title)"),
        {"id": new_id(), "tenant": tenant, "title": title},
    )


async def titles(sessions: async_sessionmaker[AsyncSession], tenant: UUID | None) -> list[str]:
    async with UnitOfWork(sessions, tenant_id=tenant) as uow:
        session = await uow.session()
        return list((await session.execute(text(f"select title from {TABLE} order by title"))).scalars())


async def test_each_tenant_sees_only_its_rows(sessions):
    async with UnitOfWork(sessions, tenant_id=TENANT_A) as uow:
        await insert(uow, TENANT_A, "a1")
    async with UnitOfWork(sessions, tenant_id=TENANT_B) as uow:
        await insert(uow, TENANT_B, "b1")
    assert await titles(sessions, TENANT_A) == ["a1"]
    assert await titles(sessions, TENANT_B) == ["b1"]
    assert await titles(sessions, None) == []


async def test_writing_into_another_tenant_is_refused(sessions):
    with pytest.raises(DBAPIError, match="row-level security"):
        async with UnitOfWork(sessions, tenant_id=TENANT_B) as uow:
            await insert(uow, TENANT_A, "stolen")
    assert await titles(sessions, TENANT_A) == []


async def test_without_tenant_nothing_can_be_written(sessions):
    with pytest.raises(DBAPIError, match="row-level security"):
        async with UnitOfWork(sessions) as uow:
            await insert(uow, TENANT_A, "orphan")


async def test_error_rolls_back_and_skips_after_commit(sessions):
    ran: list[str] = []

    async def notify() -> None:
        ran.append("sent")

    with pytest.raises(RuntimeError):
        async with UnitOfWork(sessions, tenant_id=TENANT_A) as uow:
            await insert(uow, TENANT_A, "lost")
            uow.after_commit(notify)
            raise RuntimeError("service failed")
    assert await titles(sessions, TENANT_A) == []
    assert ran == []


async def test_after_commit_runs_once_the_row_is_visible(sessions):
    seen: list[list[str]] = []

    async def check() -> None:
        seen.append(await titles(sessions, TENANT_A))

    async with UnitOfWork(sessions, tenant_id=TENANT_A) as uow:
        await insert(uow, TENANT_A, "a1")
        uow.after_commit(check)
    assert seen == [["a1"]]


async def test_tenant_scope_does_not_leak_to_the_next_transaction(sessions):
    async with UnitOfWork(sessions, tenant_id=TENANT_A) as uow:
        await insert(uow, TENANT_A, "a1")
    async with UnitOfWork(sessions) as uow:
        session = await uow.session()
        scope = (await session.execute(text("select current_setting('app.tenant_id', true)"))).scalar_one()
    assert scope in (None, "")
