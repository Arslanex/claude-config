"""
Servis sema tabanlari (ARCH-0005).

Ne yapar: `XIn` ve `XOut` semalarinin ortak ayarlarini verir.
Nasil: `FeatureIn` bilinmeyen alani reddeder ve degismezdir; `FeatureOut` ORM nesnesinden okunur.
"""

from pydantic import BaseModel, ConfigDict


class FeatureIn(BaseModel):
    """Servis girdisi."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class FeatureOut(BaseModel):
    """Servis ciktisi."""

    model_config = ConfigDict(from_attributes=True)
