"""
Her kiraci tablosunda RLS acik ve zorlanmis (ARCH-0003).

Goclerden sonra calisir (`make verify-full` once `migrate-check` yapar). `tenant_id` sutunu olan her tablo
`ENABLE` ve `FORCE` ile korunur ve en az bir politikasi vardir.
"""

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

UNPROTECTED = text(
    """
    select c.relname
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
    join pg_attribute a on a.attrelid = c.oid and a.attname = 'tenant_id' and not a.attisdropped
    where n.nspname = 'public' and c.relkind in ('r', 'p')
      and (not c.relrowsecurity or not c.relforcerowsecurity
           or not exists (select 1 from pg_policy p where p.polrelid = c.oid))
    order by c.relname
    """
)


def test_every_tenant_table_has_forced_rls(database_url):
    async def unprotected() -> list[str]:
        engine = create_async_engine(database_url)
        try:
            async with engine.connect() as connection:
                return list((await connection.execute(UNPROTECTED)).scalars())
        finally:
            await engine.dispose()

    assert asyncio.run(unprotected()) == []
