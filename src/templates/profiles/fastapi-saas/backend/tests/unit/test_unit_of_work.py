"""Is birimi ve repo tabani (ARCH-0004)."""

from uuid import UUID

import pytest
from sqlalchemy.exc import IntegrityError

from PKG_NAME.infra.database import UnitOfWork
from PKG_NAME.infra.database.models import Base, IdMixin, TenantMixin
from PKG_NAME.infra.database.repos import BaseRepo, UniqueViolation

from tests.support.fakes import FakeSession, FakeSessions

TENANT = UUID("01900000-0000-7000-8000-000000000001")


async def test_session_opens_lazily_once_and_sets_the_tenant():
    fake = FakeSession()
    sessions = FakeSessions(fake)
    uow = UnitOfWork(sessions, tenant_id=TENANT)  # type: ignore[arg-type]
    assert sessions.opened == 0
    assert await uow.session() is await uow.session()
    assert sessions.opened == 1
    statement, params = fake.calls[0][1]
    assert "set_config('app.tenant_id'" in statement and params == {"tenant_id": str(TENANT)}


async def test_without_tenant_no_scope_is_set():
    fake = FakeSession()
    await UnitOfWork(FakeSessions(fake)).session()  # type: ignore[arg-type]
    assert fake.calls == []


async def test_success_commits_runs_callbacks_and_closes(caplog):
    fake = FakeSession()
    ran: list[str] = []

    async def ok() -> None:
        ran.append("ok")

    async def broken() -> None:
        raise RuntimeError("queue down")

    async with UnitOfWork(FakeSessions(fake)) as uow:  # type: ignore[arg-type]
        await uow.session()
        uow.after_commit(broken)
        uow.after_commit(ok)
    assert fake.names() == ["commit", "close"]
    assert ran == ["ok"]
    assert "uow.after_commit_failed" in caplog.text


async def test_error_rolls_back_skips_callbacks_and_closes():
    fake = FakeSession()
    ran: list[str] = []

    async def ok() -> None:
        ran.append("ok")

    with pytest.raises(ValueError):
        async with UnitOfWork(FakeSessions(fake)) as uow:  # type: ignore[arg-type]
            await uow.session()
            uow.after_commit(ok)
            raise ValueError("boom")
    assert fake.names() == ["rollback", "close"]
    assert ran == []


async def test_failed_commit_still_closes_and_skips_callbacks():
    fake = FakeSession(commit_error=RuntimeError("commit failed"))
    ran: list[str] = []

    async def ok() -> None:
        ran.append("ok")

    with pytest.raises(RuntimeError):
        async with UnitOfWork(FakeSessions(fake)) as uow:  # type: ignore[arg-type]
            await uow.session()
            uow.after_commit(ok)
    assert fake.names() == ["commit", "close"]
    assert ran == []


async def test_unused_unit_of_work_opens_nothing():
    sessions = FakeSessions(FakeSession())
    async with UnitOfWork(sessions):  # type: ignore[arg-type]
        pass
    with pytest.raises(KeyError):
        async with UnitOfWork(sessions):  # type: ignore[arg-type]
            raise KeyError("x")
    assert sessions.opened == 0


class RepoNote(IdMixin, TenantMixin, Base):
    __tablename__ = "repo_note_probe"


class RepoTag(IdMixin, Base):
    __tablename__ = "repo_tag_probe"


class NoteRepo(BaseRepo[RepoNote]):
    model = RepoNote


class TagRepo(BaseRepo[RepoTag]):
    model = RepoTag


async def test_get_filters_by_tenant_only_on_tenant_tables():
    fake = FakeSession(result="row")
    note_id = UUID(int=1)
    assert await NoteRepo(UnitOfWork(FakeSessions(fake), tenant_id=TENANT)).get(note_id) == "row"  # type: ignore[arg-type]
    assert "tenant_id" in fake.calls[-1][1][0].split("WHERE")[1]
    await TagRepo(UnitOfWork(FakeSessions(fake), tenant_id=TENANT)).get(note_id)  # type: ignore[arg-type]
    assert "tenant_id" not in fake.calls[-1][1][0]
    await NoteRepo(UnitOfWork(FakeSessions(fake))).get(note_id)  # type: ignore[arg-type]
    assert "tenant_id" not in fake.calls[-1][1][0].split("WHERE")[1]


async def test_add_flushes_inside_a_savepoint():
    fake = FakeSession()
    record = RepoTag()
    assert await TagRepo(UnitOfWork(FakeSessions(fake))).add(record) is record  # type: ignore[arg-type]
    assert fake.names() == ["begin_nested", "add", "flush"]


class Orig(Exception):
    def __init__(self, sqlstate: str) -> None:
        super().__init__(sqlstate)
        self.sqlstate = sqlstate


async def test_add_maps_unique_violation_and_reraises_other_integrity_errors():
    duplicate = IntegrityError("insert", {}, Orig("23505"))
    with pytest.raises(UniqueViolation):
        await TagRepo(UnitOfWork(FakeSessions(FakeSession(flush_error=duplicate)))).add(RepoTag())  # type: ignore[arg-type]
    not_null = IntegrityError("insert", {}, Orig("23502"))
    with pytest.raises(IntegrityError):
        await TagRepo(UnitOfWork(FakeSessions(FakeSession(flush_error=not_null)))).add(RepoTag())  # type: ignore[arg-type]
