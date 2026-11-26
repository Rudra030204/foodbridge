"""Uniform error format: {"error": {"code": "...", "message": "..."}}."""
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    """Domain error that maps to an HTTP status and a stable machine code."""

    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message
        super().__init__(message)


def bad_request(code: str, msg: str) -> AppError:
    return AppError(400, code, msg)


def forbidden(msg: str = "You do not have permission to do this.") -> AppError:
    return AppError(403, "forbidden", msg)


def not_found(what: str = "Resource") -> AppError:
    return AppError(404, "not_found", f"{what} not found.")


def conflict(code: str, msg: str) -> AppError:
    return AppError(409, code, msg)


def _body(code: str, message: str, details=None) -> dict:
    err = {"code": code, "message": message}
    if details is not None:
        err["details"] = details
    return {"error": err}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError):
        return JSONResponse(status_code=exc.status, content=_body(exc.code, exc.message))

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException):
        codes = {401: "unauthorized", 403: "forbidden", 404: "not_found", 405: "method_not_allowed", 429: "rate_limited"}
        return JSONResponse(
            status_code=exc.status_code,
            content=_body(codes.get(exc.status_code, "http_error"), str(exc.detail)),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError):
        details = [
            {"field": ".".join(str(p) for p in e["loc"] if p != "body"), "message": e["msg"]} for e in exc.errors()
        ]
        return JSONResponse(status_code=422, content=_body("validation_error", "Invalid input.", details))

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        import logging

        logging.getLogger("foodbridge").exception("Unhandled error: %s", exc)
        return JSONResponse(status_code=500, content=_body("internal_error", "Something went wrong."))
