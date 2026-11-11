"""
Veritabani motoru.

Ne yapar: surec basina bir async motor ve session fabrikasi kurar (ARCH-0004).
Nasil: havuz sinirlari ve `statement_timeout` ayardan gelir; SQL parametreleri loglanmaz. Oturum duzeyinde durum
tutulmaz, boylece PgBouncer islem moduna gecis kod degistirmez.
"""

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from ...config import DatabaseSettings


def create_engine(settings: DatabaseSettings) -> AsyncEngine:
    """Ayardaki sinirlarla motor; adres yalniz burada acilir."""
    return create_async_engine(
        settings.database_url.get_secret_value(),
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout_seconds,
        pool_pre_ping=True,
        hide_parameters=True,
        connect_args={"server_settings": {"statement_timeout": str(settings.db_statement_timeout_ms)}},
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Commit sonrasi nesneler okunabilir kalir; otomatik flush yok."""
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
