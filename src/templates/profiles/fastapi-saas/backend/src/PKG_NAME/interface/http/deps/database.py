"""
Istek basina is birimi (ARCH-0004).

Ne yapar: route'a `UnitOfWork` verir; route basariyla bitince commit eder, hata olursa geri alir.
Nasil: `Depends(..., scope="function")` ile cikis kodu yanit gonderilmeden once calisir, boylece commit hatasi
istemciye 500 olarak doner ve basarisiz bir yazma 200 ile bildirilmez.
"""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request

from ....infra.database import UnitOfWork


async def unit_of_work(request: Request) -> AsyncIterator[UnitOfWork]:
    """Uygulama acilisinda kurulan session fabrikasiyla bir is birimi."""
    async with UnitOfWork(request.app.state.sessions) as uow:
        yield uow


UnitOfWorkDep = Annotated[UnitOfWork, Depends(unit_of_work, scope="function")]
