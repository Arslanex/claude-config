"""
Hata modeli (ARCH-0005).

Ne yapar: hata kodunu ve turunu tanimlar; feature yalniz bunlari bilir, HTTP statusunu bilmez.
Nasil: her feature `errors.py` icinde `ErrorCode` sabitleri tanimlar ve `AppError` firlatir; interface turu
statuse cevirir.
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ErrorKind(StrEnum):
    """Hatanin turu; HTTP eslemesi `interface/http/errors.py` icindedir."""

    VALIDATION = "validation"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    UNAUTHENTICATED = "unauthenticated"
    FORBIDDEN = "forbidden"
    RATE_LIMITED = "rate_limited"
    UNAVAILABLE = "unavailable"
    INTERNAL = "internal"


@dataclass(frozen=True)
class ErrorCode:
    """Sabit hata kodu: makinenin okudugu `code`, insanin okudugu `message`."""

    code: str
    kind: ErrorKind
    message: str


@dataclass
class AppError(Exception):
    """Uygulamanin bildigi hata; `details` istemciye gidebilecek, sir icermeyen ek bilgidir."""

    error: ErrorCode
    details: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"{self.error.code}: {self.error.message}"


INTERNAL_ERROR = ErrorCode("INTERNAL_ERROR", ErrorKind.INTERNAL, "Beklenmeyen bir hata olustu.")
VALIDATION_FAILED = ErrorCode("VALIDATION_FAILED", ErrorKind.VALIDATION, "Istek dogrulanamadi.")
