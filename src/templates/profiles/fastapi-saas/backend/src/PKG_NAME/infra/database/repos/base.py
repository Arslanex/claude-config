"""
Repo tabani (ARCH-0004).

Ne yapar: tablo basina repo'larin ortak okuma ve yazma yolunu verir; SQL yalniz repo'larda yazilir.
Nasil: kiraci tablosunda sorgu ayrica `tenant_id` ile suzulur. RLS asil korumadir; bu suzgec hatayi erken gosterir.
Tekillik ihlali `UniqueViolation` olarak yukari cikar, servis onu kendi hata koduna cevirir.
"""

from typing import Any, ClassVar
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError

from ..models import Base
from ..uow import UnitOfWork

UNIQUE_VIOLATION = "23505"


class UniqueViolation(Exception):
    """Ayni tekil degerle ikinci kayit."""


class BaseRepo[M: Base]:
    """Alt sinif `model` verir; metotlar ORM nesnesi doner."""

    model: ClassVar[type[Any]]

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def _scoped(self, statement: Select[Any]) -> Select[Any]:
        column = getattr(self.model, "tenant_id", None)
        if column is None or self._uow.tenant_id is None:
            return statement
        return statement.where(column == self._uow.tenant_id)

    async def get(self, record_id: UUID) -> M | None:
        """Kimlige gore tek kayit; yoksa ya da baska kiracinin ise `None`."""
        session = await self._uow.session()
        result = await session.execute(self._scoped(select(self.model).where(self.model.id == record_id)))
        return result.scalar_one_or_none()

    async def add(self, record: M) -> M:
        """Kaydi ekler ve hemen yazar; tekillik ihlali `UniqueViolation` olur."""
        session = await self._uow.session()
        try:
            async with session.begin_nested():
                session.add(record)
                await session.flush()
        except IntegrityError as error:
            if getattr(error.orig, "sqlstate", None) == UNIQUE_VIOLATION:
                raise UniqueViolation(str(error.orig)) from error
            raise
        return record
