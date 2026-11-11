"""
HTTP hata eslemesi (ARCH-0005).

Ne yapar: hata turunu HTTP statusune ceviren tek yerdir; govde her zaman `{code, message, details, trace_id}`.
Nasil: `AppError` turune gore statuse, sema dogrulama hatasi 422'ye, beklenmeyen hata 500'e doner. Dogrulama
ayrintisinda istemcinin gonderdigi deger tekrar edilmez; beklenmeyen hatanin ayrintisi yalniz loga gider.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ...core import INTERNAL_ERROR, VALIDATION_FAILED, AppError, ErrorCode, ErrorKind, current_trace_id

log = logging.getLogger(__name__)

STATUS = {
    ErrorKind.VALIDATION: 422,
    ErrorKind.NOT_FOUND: 404,
    ErrorKind.CONFLICT: 409,
    ErrorKind.UNAUTHENTICATED: 401,
    ErrorKind.FORBIDDEN: 403,
    ErrorKind.RATE_LIMITED: 429,
    ErrorKind.UNAVAILABLE: 503,
    ErrorKind.INTERNAL: 500,
}
RETRY_AFTER_SECONDS = "5"


def error_response(error: ErrorCode, details: object) -> JSONResponse:
    """Standart hata govdesi; 429 ve 503 `Retry-After` tasir."""
    status = STATUS[error.kind]
    headers = {"Retry-After": RETRY_AFTER_SECONDS} if status in (429, 503) else None
    body = {"code": error.code, "message": error.message, "details": details, "trace_id": current_trace_id()}
    return JSONResponse(body, status_code=status, headers=headers)


async def on_app_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    return error_response(exc.error, exc.details)


async def on_validation_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    fields = [{"loc": list(item["loc"]), "type": item["type"], "msg": item["msg"]} for item in exc.errors()]
    return error_response(VALIDATION_FAILED, {"fields": fields})


async def on_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    log.exception("http.unexpected_error", extra={"path": request.url.path})
    return error_response(INTERNAL_ERROR, {})


def install_error_handlers(app: FastAPI) -> None:
    """Uc isleyiciyi uygulamaya baglar."""
    app.add_exception_handler(AppError, on_app_error)
    app.add_exception_handler(RequestValidationError, on_validation_error)
    app.add_exception_handler(Exception, on_unexpected_error)
