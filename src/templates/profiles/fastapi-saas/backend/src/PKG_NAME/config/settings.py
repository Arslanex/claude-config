"""
Uygulama ayarlari.

Ne yapar: veritabani adresini ve baglanti havuzu sinirlarini ortam degiskenlerinden okur (ARCH-0002, ARCH-0004).
Nasil: pydantic-settings; yalniz giris noktalari (`interface/http/app.py`, CLI, worker) okur ve iceri parametre
olarak gecer. Adres cikti ve loglarda gorunmez.
"""

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings


class DatabaseSettings(BaseSettings):
    """Bir surecin veritabani baglantisi; toplam baglanti = kopya sayisi x (havuz + tasma)."""

    database_url: SecretStr = Field(alias="DATABASE_URL")
    db_pool_size: int = Field(default=5, ge=1, alias="DB_POOL_SIZE")
    db_max_overflow: int = Field(default=5, ge=0, alias="DB_MAX_OVERFLOW")
    db_pool_timeout_seconds: float = Field(default=5, gt=0, alias="DB_POOL_TIMEOUT_SECONDS")
    db_statement_timeout_ms: int = Field(default=10_000, ge=100, alias="DB_STATEMENT_TIMEOUT_MS")
