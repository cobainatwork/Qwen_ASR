from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Protocol

import structlog

from app.core.config import Settings
from app.core.exceptions import AsrEngineUnavailableError

logger = structlog.get_logger(__name__)


class _AsyncEngine(Protocol):
    async def generate(self, *args: Any, **kwargs: Any) -> Any: ...

    async def abort_all(self) -> None: ...


def compute_model_version(model_dir: Path) -> str:
    """產生模型版本字串。優先序：
    1. {model_dir}/version.json 內的 `version` 欄位
    2. {model_dir}/model.safetensors 的 SHA256 前 8 字元
    3. fallback "{model_dir.name}@unknown"
    """
    version_file = model_dir / "version.json"
    if version_file.is_file():
        try:
            data = json.loads(version_file.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "version" in data:
                return f"{model_dir.name}@{data['version']}"
        except (json.JSONDecodeError, OSError):
            pass

    weights = model_dir / "model.safetensors"
    if weights.is_file():
        h = hashlib.sha256()
        with weights.open("rb") as f:
            while chunk := f.read(1024 * 1024):
                h.update(chunk)
        return f"{model_dir.name}@{h.hexdigest()[:8]}"

    return f"{model_dir.name}@unknown"


class AsrEngineManager:
    """vLLM AsyncLLMEngine 單例管理。"""

    _engine: _AsyncEngine | None = None
    _model_version: str = "unknown"

    @classmethod
    async def initialize(cls, settings: Settings) -> None:
        try:
            from vllm import AsyncEngineArgs, AsyncLLMEngine
        except ImportError as e:
            raise RuntimeError(
                "vllm 套件未安裝。GPU 環境請以 INSTALL_GPU_DEPS=true 重建映像。"
            ) from e

        engine_args = AsyncEngineArgs(
            model=settings.ASR_MODEL,
            download_dir=str(settings.MODEL_CACHE_DIR),
            dtype="float16",
            gpu_memory_utilization=settings.VLLM_GPU_MEMORY_UTILIZATION,
            max_num_seqs=settings.MAX_INFERENCE_BATCH,
            max_model_len=settings.ASR_MAX_TOKENS,
        )
        cls._engine = AsyncLLMEngine.from_engine_args(engine_args)
        model_dir = settings.MODEL_CACHE_DIR / settings.ASR_MODEL.replace("/", "_")
        cls._model_version = compute_model_version(model_dir)
        logger.info("ASR engine initialized", model_version=cls._model_version)

    @classmethod
    def set_engine_for_test(
        cls, engine: _AsyncEngine | None, model_version: str = "MOCK@TEST"
    ) -> None:
        cls._engine = engine
        cls._model_version = model_version

    @classmethod
    async def shutdown(cls) -> None:
        if cls._engine is not None:
            try:
                await cls._engine.abort_all()
            except Exception as e:
                logger.warning("engine abort_all failed", error=str(e))
            cls._engine = None

    @classmethod
    def get_engine(cls) -> _AsyncEngine:
        if cls._engine is None:
            raise AsrEngineUnavailableError()
        return cls._engine

    @classmethod
    def model_version(cls) -> str:
        return cls._model_version
