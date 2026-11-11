"""
Kimlik standardi.

Ne yapar: butun kayitlar icin UUIDv7 uretir; zamana gore siralanir, indeks dostudur (ARCH-0004).
Nasil: RFC 9562 duzeni; 48 bit milisaniye zaman damgasi, surum ve varyant bitleri, kalan bitler rastgele.
"""

import os
import time
import uuid


def new_id() -> uuid.UUID:
    """Yeni bir UUIDv7."""
    millis = time.time_ns() // 1_000_000
    value = (millis & 0xFFFF_FFFF_FFFF) << 80 | int.from_bytes(os.urandom(10), "big")
    value = value & ~(0xF << 76) | 0x7 << 76
    value = value & ~(0x3 << 62) | 0x2 << 62
    return uuid.UUID(int=value)
