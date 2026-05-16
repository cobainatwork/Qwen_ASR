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
        v = ValidationFailedError(details={"errors": exc.errors()})
        logger.warning("Validation error", path=request.url.path, errors=exc.errors())
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
