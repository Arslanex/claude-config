"""HTTP hata eslemesi ve istek kimligi (ARCH-0005, ARCH-0007)."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from PKG_NAME.core import AppError, ErrorCode, ErrorKind
from PKG_NAME.interface.http.errors import STATUS, install_error_handlers
from PKG_NAME.interface.http.middleware import RequestIdMiddleware

NOT_FOUND = ErrorCode("NOTE_NOT_FOUND", ErrorKind.NOT_FOUND, "Not bulunamadi.")
BUSY = ErrorCode("BUSY", ErrorKind.UNAVAILABLE, "Mesgul.")


class Body(BaseModel):
    title: str


def client() -> TestClient:
    app = FastAPI()
    install_error_handlers(app)
    app.add_middleware(RequestIdMiddleware)

    @app.get("/missing")
    async def missing() -> None:
        raise AppError(NOT_FOUND, {"id": "1"})

    @app.get("/busy")
    async def busy() -> None:
        raise AppError(BUSY)

    @app.post("/notes")
    async def create(body: Body) -> Body:
        return body

    @app.get("/crash")
    async def crash() -> None:
        raise RuntimeError("password=hunter2")

    return TestClient(app, raise_server_exceptions=False)


def test_every_error_kind_has_a_status():
    assert set(STATUS) == set(ErrorKind)


def test_app_error_maps_kind_to_status_with_the_standard_body():
    response = client().get("/missing", headers={"X-Request-Id": "req-1"})
    assert response.status_code == 404
    assert response.json() == {
        "code": "NOTE_NOT_FOUND",
        "message": "Not bulunamadi.",
        "details": {"id": "1"},
        "trace_id": "req-1",
    }
    assert "retry-after" not in response.headers


def test_unavailable_sends_retry_after():
    response = client().get("/busy")
    assert response.status_code == 503
    assert response.headers["retry-after"] == "5"


def test_validation_error_lists_fields_without_echoing_input():
    response = client().post("/notes", json={"title": 123, "secret": "s3cret-value"})
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "VALIDATION_FAILED"
    assert body["details"]["fields"][0]["loc"] == ["body", "title"]
    assert "s3cret-value" not in response.text and "123" not in response.text


def test_unexpected_error_is_500_without_internals(caplog):
    response = client().get("/crash")
    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_ERROR"
    assert "hunter2" not in response.text
    assert "http.unexpected_error" in caplog.text


def test_request_id_is_echoed_when_safe_and_generated_otherwise():
    http = client()
    assert http.get("/missing", headers={"X-Request-Id": "abc.DEF_1-2"}).headers["x-request-id"] == "abc.DEF_1-2"
    for unsafe in ("bad id", "x" * 65, ""):
        generated = http.get("/missing", headers={"X-Request-Id": unsafe}).headers["x-request-id"]
        assert generated != unsafe and len(generated) == 32
    assert len(http.get("/missing").headers["x-request-id"]) == 32


@pytest.mark.parametrize("scope_type", ["lifespan", "websocket"])
async def test_middleware_passes_non_http_scopes_through(scope_type):
    seen: list[str] = []

    async def inner(scope, receive, send):
        seen.append(scope["type"])

    await RequestIdMiddleware(inner)({"type": scope_type}, None, None)  # type: ignore[arg-type]
    assert seen == [scope_type]
