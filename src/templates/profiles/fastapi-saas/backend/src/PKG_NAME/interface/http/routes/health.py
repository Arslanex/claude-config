"""
Saglik uclari.

Ne yapar: `/health` surecin ayakta oldugunu, `/ready` veritabanina erisimi ve semanin guncel oldugunu soyler.
Nasil: `/health` hicbir bagimlilik yoklamaz; `/ready` denetimi `deps` icindedir, sorun varsa 503 doner.
"""

from typing import Literal

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from ..deps import readiness

router = APIRouter(tags=["health"])


class HealthOut(BaseModel):
    """Saglik yaniti."""

    status: Literal["ok"] = "ok"


class ReadyOut(BaseModel):
    """Hazir olma yaniti; her denetim `ok` ya da sorunun adi."""

    status: Literal["ready", "not_ready"]
    checks: dict[str, str]


@router.get("/health")
async def health() -> HealthOut:
    """Surec yanit veriyorsa `ok`."""
    return HealthOut()


@router.get("/ready", responses={503: {"model": ReadyOut}})
async def ready(request: Request, response: Response) -> ReadyOut:
    """Butun denetimler `ok` ise 200, degilse 503."""
    checks = await readiness(request.app.state.engine, request.app.state.migration_heads)
    is_ready = all(value == "ok" for value in checks.values())
    response.status_code = 200 if is_ready else 503
    return ReadyOut(status="ready" if is_ready else "not_ready", checks=checks)
