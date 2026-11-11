"""
Is birimi (ARCH-0004, ARCH-0005).

Ne yapar: istek, komut ya da mesaj basina tek veritabani islemi acar; basarida commit, hatada geri alir.
Nasil: oturum ilk kullanimda acilir ve kiraci kapsami `set_config(..., true)` ile yalniz bu isleme verilir (RLS,
ARCH-0003). Commit sonrasi isler (kuyruga yazma, e-posta) `after_commit` ile kaydedilir ve yalniz commit basariliysa
calisir; birinin hatasi loglanir, digerlerini durdurmaz. Servis commit etmez; bunu cagiran katman yapar.
"""

import logging
from collections.abc import Awaitable, Callable
from types import TracebackType
from typing import Self
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

log = logging.getLogger(__name__)

AfterCommit = Callable[[], Awaitable[None]]


class UnitOfWork:
    """`async with UnitOfWork(...) as uow:` bir islem; servis `await uow.session()` ile oturumu alir."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession], *, tenant_id: UUID | None = None) -> None:
        self._sessions = sessions
        self.tenant_id = tenant_id
        self._session: AsyncSession | None = None
        self._after_commit: list[AfterCommit] = []

    async def session(self) -> AsyncSession:
        """Bu islemin oturumu; ilk cagrida acilir ve kiraci kapsami kurulur."""
        if self._session is None:
            self._session = self._sessions()
            if self.tenant_id is not None:
                await self._session.execute(
                    text("select set_config('app.tenant_id', :tenant_id, true)"), {"tenant_id": str(self.tenant_id)}
                )
        return self._session

    def after_commit(self, callback: AfterCommit) -> None:
        """Commit basarili olursa calisacak isi kaydeder."""
        self._after_commit.append(callback)

    async def commit(self) -> None:
        """Islemi kalici yapar, ardindan kayitli isleri sirayla calistirir."""
        if self._session is not None:
            await self._session.commit()
        callbacks, self._after_commit = self._after_commit, []
        for callback in callbacks:
            try:
                await callback()
            except Exception:
                log.exception("uow.after_commit_failed")

    async def rollback(self) -> None:
        """Islemi geri alir; kayitli isler calismaz."""
        self._after_commit = []
        if self._session is not None:
            await self._session.rollback()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self, kind: type[BaseException] | None, error: BaseException | None, trace: TracebackType | None
    ) -> None:
        try:
            if error is None:
                await self.commit()
            else:
                await self.rollback()
        finally:
            if self._session is not None:
                await self._session.close()
                self._session = None
