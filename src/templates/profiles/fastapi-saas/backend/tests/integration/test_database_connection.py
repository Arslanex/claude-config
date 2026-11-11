"""Test stack'indeki veritabanina async surucu ile baglanilabildigini dogrular."""

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


def test_database_answers_a_query(database_url):
    async def probe() -> int:
        engine = create_async_engine(database_url)
        try:
            async with engine.connect() as connection:
                return (await connection.execute(text("select 1"))).scalar_one()
        finally:
            await engine.dispose()

    assert asyncio.run(probe()) == 1
