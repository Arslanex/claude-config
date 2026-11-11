import os

import pytest


@pytest.fixture(scope="session")
def database_url():
    return os.environ.get("TEST_DATABASE_URL", "postgresql+asyncpg://test:test@localhost:55463/test")


@pytest.fixture(scope="session")
def redis_url():
    return os.environ.get("TEST_REDIS_URL", "redis://localhost:56410/0")
