from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.exceptions import AppException, ValidationFailedError
from app.core.response import failure

logger = structlog.get_logger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppException)
    async def _app_exc(request: Request, exc: AppException) -> JSONResponse:
        logger.warning(
            "Request failed",
            error_code=exc.code,
            path=request.url.path,
            method=request.method,
        )
        return JSONResponse(
            status_code=exc.http_status,
            content=failure(exc.code, exc.message, exc.details).model_dump(),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_exc(request: Request, exc: RequestValidationError) -> JSONResponse:
        def _sanitize(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
            """Convert non-JSON-serializable values in pydantic error dicts to strings.

            Pydantic v2 model_validator(mode='after') errors include a 'ctx' key
            whose 'error' value is the raw Exception instance, which is not
            JSON-serializable.  Stringify it so JSONResponse does not crash.
            """
            result = []
            for err in errors:
                sanitized = dict(err)
                if "ctx" in sanitized:
                    ctx = sanitized["ctx"]
                    sanitized["ctx"] = {
                        k: str(v) if isinstance(v, Exception) else v
                        for k, v in ctx.items()
                    }
                result.append(sanitized)
            return result

        sanitized_errors = _sanitize(list(exc.errors()))
        v = ValidationFailedError(details={"errors": sanitized_errors})
        logger.warning("Validation error", path=request.url.path, errors=sanitized_errors)
        return JSONResponse(
            status_code=v.http_status,
            content=failure(v.code, v.message, v.details).model_dump(),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception", path=request.url.path)
        return JSONResponse(
            status_code=500,
            content=failure("INTERNAL_ERROR", "伺服器內部錯誤").model_dump(),
        )
