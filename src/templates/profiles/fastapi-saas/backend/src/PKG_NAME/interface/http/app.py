"""
HTTP uygulamasi.

Ne yapar: FastAPI uygulamasini kurar; hata eslemesini, istek kimligini ve route modullerini baglar.
Nasil: ayar yalniz burada okunur (ARCH-0007). Motor ve session fabrikasi acilista bir kez kurulur ve
`app.state` uzerinden `deps`'e gecer; kapanista motor kapatilir. Is kurali burada durmaz (ARCH-0006).
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from ...config import DatabaseSettings, DeploymentSettings
from ...infra.database import TenantRouter, create_engine, create_session_factory
from .deps import code_heads
from .errors import install_error_handlers
from .middleware import RequestIdMiddleware
from .routes import ROUTERS


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Acilista baglanti havuzu, kapanista temizlik."""
    engine = create_engine(DatabaseSettings())  # type: ignore[call-arg]
    tenants = TenantRouter(DeploymentSettings(), create_session_factory(engine))
    application.state.engine = engine
    application.state.sessions = tenants.sessions()
    application.state.migration_heads = code_heads()
    try:
        yield
    finally:
        await engine.dispose()


def create_app() -> FastAPI:
    """Uygulamayi kurar; testler ve `make openapi` ayni fabrikayi kullanir."""
    application = FastAPI(title="PKG_NAME", lifespan=lifespan)
    install_error_handlers(application)
    application.add_middleware(RequestIdMiddleware)
    for router in ROUTERS:
        application.include_router(router)
    return application


app = create_app()
