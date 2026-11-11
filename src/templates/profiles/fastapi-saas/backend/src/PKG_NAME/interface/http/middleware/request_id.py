"""
Istek kimligi (ARCH-0007).

Ne yapar: `X-Request-Id` basligini istegin `trace_id` degeri yapar ve yanita geri yazar.
Nasil: gelen deger yalniz guvenli karakterlerden olusuyor ve 64 karakteri gecmiyorsa kullanilir, yoksa yenisi
uretilir; deger istek suresince `TRACE_ID` icindedir.
"""

import re

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ....core import TRACE_ID, new_id

HEADER = b"x-request-id"
SAFE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class RequestIdMiddleware:
    """Saf ASGI middleware; govdeyi tamponlamaz."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = dict(scope["headers"]).get(HEADER, b"").decode("latin-1")
        trace_id = incoming if SAFE.match(incoming) else new_id().hex
        token = TRACE_ID.set(trace_id)

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                message["headers"] = [*message.get("headers", []), (HEADER, trace_id.encode("latin-1"))]
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            TRACE_ID.reset(token)
