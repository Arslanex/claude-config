"""
API sozlesmesini yazar.

Ne yapar: uygulamanin OpenAPI semasini deterministik JSON olarak standart ciktiya basar (`make openapi`).
Nasil: `create_app()` semasi anahtarlari sirali, iki bosluk girintili yazilir; fark kontrolu bayt bayt yapilabilir.
"""

import json

from ..http.app import create_app


def render() -> str:
    """Sozlesme metni (ARCH-0007)."""
    return json.dumps(create_app().openapi(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


if __name__ == "__main__":  # pragma: no cover
    print(render(), end="")
