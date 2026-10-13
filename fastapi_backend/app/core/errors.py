"""
One error format for every API response with a 4xx or 5xx status.

Every error body has two top-level fields the mobile app can rely on:
- code: stable machine-readable string, e.g. "not_found", "outside_geofence"
- message: human-readable text, safe to show to the user

Fields the web app already reads (`detail`, and `error` on face routes)
are kept unchanged, so this is additive.
"""
import logging
from http import HTTPStatus

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


logger = logging.getLogger(__name__)


STATUS_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "payload_too_large",
    422: "validation_error",
    428: "precondition_required",
    429: "too_many_requests",
    500: "internal_error",
    502: "bad_gateway",
    503: "service_unavailable",
}


class ApiError(HTTPException):
    """HTTPException with a specific error code instead of the status default."""

    def __init__(self, status_code: int, code: str, detail, headers=None):
        super().__init__(status_code=status_code, detail=detail, headers=headers)
        self.code = code


def _default_code(status_code: int) -> str:
    return STATUS_CODES.get(status_code, "error" if status_code < 500 else "internal_error")


def _default_message(status_code: int) -> str:
    try:
        return HTTPStatus(status_code).phrase
    except ValueError:
        return "Error"


def error_body(status_code: int, body, code: str | None = None) -> dict:
    """
    Add `code` and `message` to an error body without removing its fields.
    `body` may be a dict (kept as-is) or anything else (put under `detail`).
    """
    content = dict(body) if isinstance(body, dict) else {"detail": body}

    source = content.get("detail") if isinstance(content.get("detail"), dict) else content

    if code is None:
        code = source.get("code") if isinstance(source.get("code"), str) else None
    content["code"] = code or _default_code(status_code)

    message = None
    for key in ("message", "error", "detail"):
        value = source.get(key)
        if isinstance(value, str) and value:
            message = value
            break
    content["message"] = message or _default_message(status_code)

    return content


def error_response(status_code: int, body, code: str | None = None) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=error_body(status_code, body, code))


async def _http_exception_handler(request: Request, exc: StarletteHTTPException):
    content = error_body(
        exc.status_code,
        {"detail": jsonable_encoder(exc.detail)},
        getattr(exc, "code", None),
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=content,
        headers=getattr(exc, "headers", None),
    )


async def _validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = jsonable_encoder(exc.errors())
    message = "Invalid request"
    if errors:
        first = errors[0]
        field = ".".join(str(part) for part in first.get("loc", []) if part != "body")
        message = f"{field}: {first.get('msg')}" if field else str(first.get("msg"))
    return JSONResponse(
        status_code=422,
        content={"detail": errors, "code": "validation_error", "message": message},
    )


async def _unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "code": "internal_error",
            "message": "Something went wrong. Please try again.",
        },
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_exception_handler)
    app.add_exception_handler(Exception, _unhandled_exception_handler)
