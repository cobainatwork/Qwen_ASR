"""ForcedAligner 模組級單例。

切段限制：5 分鐘（規格 §3.3.2）。長音檔分段處理，回傳 list[WordTimestamp]。
"""

# ---------------------------------------------------------------------------
# DEPRECATED 主流程依賴（M4-revisit 2026-05-18）
#
# ForcedAligner 已內建於 Qwen3ASRModel.LLM（qwen-asr 套件），
# transcribe 主流程直接從 result.time_stamps 取得對齊結果。
#
# 本模組僅保留為 **offline 批次校正工具**（規格 v1.10 §3.3.2 歷史保留說明）：
# - 使用場景：批次校正工作台需要對長音檔做精細詞級對齊時
# - 啟用控制：ALIGNER_ENABLED=True（預設 False）
# - 切段限制：5 分鐘（ALIGNER_MAX_DURATION_SEC=300）
#
# 若您在 transcribe pipeline 看到對此模組的直接呼叫，屬於 bug。
# ---------------------------------------------------------------------------


from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import structlog

from app.core.config import Settings
from app.core.exceptions import AlignerAudioTooLongError, AlignerNotReadyError

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class WordTimestamp:
    word: str
    start_sec: float
    end_sec: float


class _AlignerEngine(Protocol):
    def align(self, text: str, wav_path: str) -> list[tuple[str, float, float]]: ...


class AlignerService:
    """Qwen3-ForcedAligner 單例。"""

    _engine: _AlignerEngine | None = None
    _max_duration_sec: int = 300

    @classmethod
    def load(cls, settings: Settings) -> None:
        from app.services.aligner._loader import load_aligner

        loaded = load_aligner(settings.ALIGNER_MODEL_PATH)
        # 將 raw transformers model 包裝為 _AlignerEngine
        # 實際包裝邏輯依官方 release，本 plan 提供占位。
        cls._engine = _TransformersAlignerWrapper(loaded["model"], loaded["processor"])
        cls._max_duration_sec = settings.ALIGNER_MAX_DURATION_SEC
        logger.info("AlignerService loaded", max_duration_sec=cls._max_duration_sec)

    @classmethod
    def set_engine_for_test(
        cls, engine: _AlignerEngine | None, max_duration_sec: int = 300
    ) -> None:
        cls._engine = engine
        cls._max_duration_sec = max_duration_sec

    @classmethod
    async def align(cls, text: str, wav_path: Path, duration_sec: float) -> list[WordTimestamp]:
        if cls._engine is None:
            raise AlignerNotReadyError()
        if duration_sec > cls._max_duration_sec:
            raise AlignerAudioTooLongError(
                details={"limit_sec": cls._max_duration_sec, "actual_sec": duration_sec}
            )
        raw = await asyncio.to_thread(cls._engine.align, text, str(wav_path))
        return [WordTimestamp(word=w, start_sec=s, end_sec=e) for w, s, e in raw]


class _TransformersAlignerWrapper:
    """將 transformers AutoModel 包裝為 _AlignerEngine 介面。

    實際對齊邏輯依 Qwen3-ForcedAligner 官方 release 補完。本占位提供結構。
    """

    def __init__(self, model: Any, processor: Any) -> None:
        self.model = model
        self.processor = processor

    def align(self, text: str, wav_path: str) -> list[tuple[str, float, float]]:
        # 占位：實際對齊呼叫 self.processor(...) + self.model.forward(...)
        # 本 milestone 不執行真實 GPU 對齊；測試走 mock。
        raise NotImplementedError(
            "Qwen3-ForcedAligner 對齊邏輯需依官方 API 補完；目前透過 set_engine_for_test 注入 mock"
        )
