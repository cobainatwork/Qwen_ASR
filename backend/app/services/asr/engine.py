from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import structlog

from app.core.config import Settings
from app.core.exceptions import AsrEngineUnavailableError

logger = structlog.get_logger(__name__)

# qwen-asr 僅在 GPU 環境（INSTALL_GPU_DEPS=true）安裝；CPU CI 無此套件。
# Module-level import + None fallback：
#   1. CPU CI 仍可 import 本模組（不會 ImportError 中斷 Settings / 其他依賴模組）
#   2. 單元測試可用 unittest.mock.patch("app.services.asr.engine.Qwen3ASRModel") 注入 mock
try:
    from qwen_asr import Qwen3ASRModel  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - CPU CI path
    Qwen3ASRModel = None  # type: ignore[assignment,misc]

_DTYPE_MAP: dict[str, Any] = {}


def _get_dtype_map() -> dict[str, Any]:
    """惰性初始化 dtype 對照表，避免頂層 import torch（CPU CI 無 torch）。"""
    if not _DTYPE_MAP:
        import torch  # noqa: PLC0415

        _DTYPE_MAP["bfloat16"] = torch.bfloat16
        _DTYPE_MAP["float16"] = torch.float16
        _DTYPE_MAP["float32"] = torch.float32
    return _DTYPE_MAP


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
    """Qwen3ASRModel.LLM 單例管理（v1.10 §3.3.1 / §3.3.2）。

    非同步包裝說明：qwen-asr 0.0.6 的 transcribe() 為同步阻塞呼叫，
    FastAPI 層透過 asyncio.to_thread 包裝（見 transcriber.py）。
    本管理器只負責初始化與生命週期，不做 async 包裝。
    """

    _asr: Any | None = None
    _model_version: str = "unknown"

    @classmethod
    def initialize(cls, settings: Settings) -> None:
        """建立 Qwen3ASRModel.LLM 實例並儲存為單例。

        GPU 環境需安裝 qwen-asr[vllm] extra（INSTALL_GPU_DEPS=true）。
        ForcedAligner 已內建於 Qwen3ASRModel.LLM（規格 v1.10 §3.3.2）。
        """
        if Qwen3ASRModel is None:
            raise RuntimeError(
                "qwen-asr 套件未安裝。GPU 環境請以 INSTALL_GPU_DEPS=true 重建映像。"
            )

        dtype_map = _get_dtype_map()
        dtype = dtype_map.get(settings.FORCED_ALIGNER_DTYPE)
        if dtype is None:
            raise RuntimeError(
                f"FORCED_ALIGNER_DTYPE 不合法：{settings.FORCED_ALIGNER_DTYPE}，"
                f"需為 bfloat16 / float16 / float32 其一"
            )

        forced_aligner_kwargs: dict[str, Any] = {
            "dtype": dtype,
            "device_map": settings.FORCED_ALIGNER_DEVICE,
        }

        cls._asr = Qwen3ASRModel.LLM(
            settings.ASR_MODEL,
            gpu_memory_utilization=settings.VLLM_GPU_MEMORY_UTILIZATION,
            max_inference_batch_size=settings.MAX_INFERENCE_BATCH,
            max_new_tokens=settings.ASR_MAX_TOKENS,
            forced_aligner=settings.FORCED_ALIGNER_MODEL,
            forced_aligner_kwargs=forced_aligner_kwargs,
            download_dir=str(settings.MODEL_CACHE_DIR),
        )

        model_dir = settings.MODEL_CACHE_DIR / settings.ASR_MODEL.replace("/", "_")
        cls._model_version = compute_model_version(model_dir)
        logger.info("ASR engine initialized", model_version=cls._model_version)

    @classmethod
    def set_asr_for_test(
        cls, asr: Any | None, model_version: str = "unknown"
    ) -> None:
        """測試注入點：reset internal state，預設 model_version 為 'unknown'，
        與 shutdown() 後狀態一致。asr=None 等同 shutdown 效果。
        """
        cls._asr = asr
        cls._model_version = model_version

    @classmethod
    def shutdown(cls) -> None:
        """釋放 ASR 引擎。qwen-asr 無官方 dispose 方法；設為 None 觸發 GC。"""
        if cls._asr is not None:
            logger.info("ASR engine shutdown")
            cls._asr = None
        cls._model_version = "unknown"

    @classmethod
    def get_asr(cls) -> Any:
        """取得 Qwen3ASRModel.LLM 實例。未初始化時拋 AsrEngineUnavailableError。"""
        if cls._asr is None:
            raise AsrEngineUnavailableError()
        return cls._asr

    @classmethod
    def model_version(cls) -> str:
        return cls._model_version
