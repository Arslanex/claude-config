"""
Dagitim modu ayarlari (ARCH-0003).

Ne yapar: DEPLOYMENT_TENANCY ve DEPLOYMENT_TOPOLOGY ortam degiskenlerini okur.
Nasil: pydantic-settings; tanimsiz bir deger acilista dogrulama hatasi verir.
"""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class DeploymentSettings(BaseSettings):
    """Iki bagimsiz eksen: tenancy ve topology."""

    model_config = SettingsConfigDict(env_prefix="DEPLOYMENT_")

    tenancy: Literal["shared_rls", "db_per_tenant"] = "shared_rls"
    topology: Literal["saas", "dedicated", "on_prem"] = "saas"
