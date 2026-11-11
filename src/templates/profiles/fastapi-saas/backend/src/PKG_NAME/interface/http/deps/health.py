"""
Hazir olma denetimi (ARCH-0002).

Ne yapar: veritabanina erisimi ve semanin koddaki goc basiyla ayni olup olmadigini soyler.
Nasil: `select version_num from alembic_version` sonucu, `migrations/` dizinindeki goc basiyla karsilastirilir.
Kurulum `/ready` yesil olmadan trafigi bu kopyaya cevirmez.
"""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

BACKEND = Path(__file__).resolve().parents[5]


def code_heads(backend: Path = BACKEND) -> set[str]:
    """Kodun bekledigi goc basi (birden cok bas varsa hepsi)."""
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "migrations"))
    return set(ScriptDirectory.from_config(config).get_heads())


async def readiness(engine: AsyncEngine, expected: set[str]) -> dict[str, str]:
    """
    `database` ve `schema` icin `ok` ya da sorunun adi.

    Goc tablosu hic yoksa uygulanan goc yok sayilir; baglanti kurulamazsa sema `skipped` olur. Hata ayrintisi yanita
    yazilmaz.
    """
    try:
        async with engine.connect() as connection:
            rows = await connection.execute(text("select version_num from alembic_version"))
            applied = {row[0] for row in rows}
    except ProgrammingError:
        applied = set()
    except (OSError, SQLAlchemyError):
        return {"database": "unreachable", "schema": "skipped"}
    return {"database": "ok", "schema": "ok" if applied == expected else "behind"}
