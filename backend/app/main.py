from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging, get_logger
from app.core.startup_checks import run_startup_checks
from app.deps.db import get_session_factory
from app.middleware import (
    idempotency_middleware,
    prometheus_middleware,
    rate_limit_middleware,
    register_exception_handlers,
    request_id_middleware,
    tracing_middleware,
)
from app.routers.health import router as health_router
from app.services.bootstrap import bootstrap_admin_key


def _configure_app(settings: Settings) -> FastAPI:
    configure_logging(level=settings.LOG_LEVEL, json_format=settings.LOG_FORMAT == "json")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        logger = get_logger("startup")
        logger.info("backend lifespan start", env=settings.ENV)
        run_startup_checks(settings)
        with get_session_factory()() as db:
            bootstrap_admin_key(db, settings)
        yield
        logger.info("backend lifespan stop")

    app = FastAPI(
        title="Qwen3-ASR API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.OPENAPI_DOCS_ENABLED else None,
        redoc_url=None,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 自訂 middleware（順序：request_id → tracing → prometheus → rate_limit → idempotency）
    app.middleware("http")(idempotency_middleware)
    app.middleware("http")(rate_limit_middleware)
    app.middleware("http")(prometheus_middleware)
    app.middleware("http")(tracing_middleware)
    app.middleware("http")(request_id_middleware)

    register_exception_handlers(app)
    app.include_router(health_router)
    return app


def create_app() -> FastAPI:
    return _configure_app(get_settings())


app = create_app()
