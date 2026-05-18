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
from app.routers.asr import router as asr_router
from app.routers.dataset import router as dataset_router
from app.routers.health import router as health_router
from app.routers.hotword import router as hotword_router
from app.services.asr.consumer import AsrConsumer
from app.services.asr.engine import AsrEngineManager
from app.services.asr.queue import AsyncioQueueBackend
from app.services.audio.vad import FireRedVADService
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

        # 載入 VAD（Phase 1 必載）
        if settings.VAD_ENABLED:
            try:
                FireRedVADService.load(settings.VAD_MODEL_DIR)
            except RuntimeError as e:
                if settings.ENV == "production":
                    raise
                logger.warning("VAD load failed (development tolerated)", error=str(e))

        # 載入 vLLM
        try:
            AsrEngineManager.initialize(settings)
        except RuntimeError as e:
            if settings.ENV == "production":
                raise
            logger.warning("qwen-asr initialize skipped (development)", error=str(e))
        # 注意：ForcedAligner 已內建於 Qwen3ASRModel.LLM（qwen-asr §3.3.2）
        # AlignerService 不再在 lifespan 載入；offline 批次校正由 ALIGNER_ENABLED 控制

        # M7：載入 Diarization（dev 容忍 ImportError）
        if settings.DIARIZATION_ENABLED:
            try:
                from app.services.diarization import DiarizationService
                DiarizationService.load(settings)
            except RuntimeError as e:
                if settings.ENV == "production":
                    raise
                logger.warning("DiarizationService load skipped (development)", error=str(e))

        # KenLM（可選）
        if settings.CORRECTION_KENLM_ENABLED and settings.CORRECTION_KENLM_MODEL_PATH:
            try:
                from app.services.correction.kenlm_corrector import KenlmCorrector
                KenlmCorrector.load(settings.CORRECTION_KENLM_MODEL_PATH)
            except RuntimeError as e:
                logger.warning("KenLM load skipped", error=str(e))

        # Homophone（純 CPU 配置）
        if settings.CORRECTION_HOMOPHONE_ENABLED:
            from app.services.correction.homophone import HomophoneCorrector
            HomophoneCorrector.configure(True)

        # 啟動 ASR 佇列與 consumer
        queue = AsyncioQueueBackend(
            realtime_max=settings.QUEUE_REALTIME_MAX_SIZE,
            batch_max=settings.QUEUE_BATCH_MAX_SIZE,
        )
        app.state.asr_queue = queue
        consumer = AsrConsumer(queue, max_duration_sec=settings.ASR_AUDIO_MAX_DURATION_SEC)
        await consumer.start()
        app.state.asr_consumer = consumer

        yield

        await consumer.stop()
        AsrEngineManager.shutdown()
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
    app.include_router(asr_router)
    app.include_router(hotword_router)
    app.include_router(dataset_router)

    if settings.DEPLOYMENT_PROFILE == "vendor":
        from app.routers.correction import router as correction_router
        from app.routers.finetune import router as finetune_router
        from app.routers.youtube import router as youtube_router
        app.include_router(finetune_router)
        app.include_router(youtube_router)
        app.include_router(correction_router)

    return app


def create_app() -> FastAPI:
    return _configure_app(get_settings())


app = create_app()
