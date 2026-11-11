"""
Worker modu ayari (ARCH-0007).

Ne yapar: WORKER_MODE ortam degiskenini okur (`fake` ya da `live`, varsayilan `fake`) ve dis kapinin sahte ya da
gercek adaptorunu secer.
Nasil: pydantic-settings; modu yalniz `pick` okur. Giris noktasi ucretli ya da dis her kapiyi (LLM, odeme, mail)
`pick` ile kurar. Testler hep `fake` ile calisir; gercek servis testlerini yalniz kullanici calistirir.
"""

from collections.abc import Callable
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings


class WorkerSettings(BaseSettings):
    """Her dis kapinin adaptorunu secer; tanimsiz bir deger acilista dogrulama hatasi verir."""

    worker_mode: Literal["fake", "live"] = Field(default="fake", alias="WORKER_MODE")

    def pick[T](self, live: Callable[[], T], fake: Callable[[], T]) -> T:
        """Yalniz secilen adaptoru kurar; sahte modda gercek istemci hic olusmaz."""
        return live() if self.worker_mode == "live" else fake()
