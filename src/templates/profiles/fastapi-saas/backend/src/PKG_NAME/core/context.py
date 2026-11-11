"""
Istek baglami.

Ne yapar: istegin iz kimligini (`trace_id`) log, hata govdesi ve kuyruk zarfi icin tasir (ARCH-0007).
Nasil: `contextvars`; her istek ya da is kendi degerini kurar, surecler arasi durum tutulmaz.
"""

from contextvars import ContextVar

TRACE_ID: ContextVar[str] = ContextVar("trace_id", default="")


def current_trace_id() -> str:
    """Bu istegin iz kimligi; kurulmadiysa bos metin."""
    return TRACE_ID.get()
