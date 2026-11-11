"""
Kiraci yonlendirici (ARCH-0003).

Ne yapar: bir kiracinin hangi veritabanina gidecegini soyler; `DEPLOYMENT_TENANCY` yalniz burada okunur.
Nasil: `shared_rls` modunda tek session fabrikasi doner ve ayrim RLS ile yapilir. `db_per_tenant` modunun arayuzu
hazirdir, uygulamasi sonra yazilir; o zamana kadar acilista acik bir hata verir.
"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ...config import DeploymentSettings


class TenantRouter:
    """Kiraci basina session fabrikasi."""

    def __init__(self, deployment: DeploymentSettings, shared: async_sessionmaker[AsyncSession]) -> None:
        if deployment.tenancy != "shared_rls":
            raise NotImplementedError("DEPLOYMENT_TENANCY=db_per_tenant henuz uygulanmadi (ARCH-0003)")
        self._shared = shared

    def sessions(self) -> async_sessionmaker[AsyncSession]:
        """Bu kiracinin session fabrikasi; `shared_rls` modunda hepsi icin aynidir."""
        return self._shared
