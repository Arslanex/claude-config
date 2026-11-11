"""
ORM modelleri. interface katmani bunu dogrudan import etmez (ARCH-0005).

Ne yapar: tum modellerin turedigi Base sinifini ve kisit adlandirma standardini tanimlar.
Nasil: MetaData naming_convention; alembic autogenerate her ortamda ayni kisit adini uretir. Ortak sutunlar
karisim siniflaridir: kimlik UUIDv7, zaman `timestamptz` (UTC), kiraci tablosunda `tenant_id` ve RLS (ARCH-0003).
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from ...core import new_id

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Tum ORM modellerinin tabani."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class IdMixin:
    """Uygulamada uretilen UUIDv7 birincil anahtar."""

    id: Mapped[UUID] = mapped_column(primary_key=True, default=new_id)


class TimestampMixin:
    """Olusturma ve guncelleme zamani, veritabaninda UTC."""

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TenantMixin:
    """Kiraciya ait tablo; gocte `tenant_rls_statements` ile RLS acilir."""

    tenant_id: Mapped[UUID] = mapped_column(index=True)
