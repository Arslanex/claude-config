"""Route modulleri: her feature grubu icin bir modul ya da paket (ARCH-0006)."""

from .health import router as health_router

ROUTERS = (health_router,)

__all__ = ["ROUTERS"]
