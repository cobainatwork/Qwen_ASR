from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.core.exceptions import (
    AudioNoSpeechError,
    AudioVadFailedError,
    AudioVadNotReadyError,
)


@dataclass(frozen=True)
class Segment:
    start_sec: float
    end_sec: float


class _VadEngine(Protocol):
    """FireRedVAD 模型介面（用於型別檢查與 mock）。"""

    def infer(self, wav_path: str) -> list[tuple[float, float]]: ...


class FireRedVADService:
    """FireRedVAD 模組級單例。於 FastAPI lifespan 啟動載入。"""

    _model: _VadEngine | None = None

    @classmethod
    def load(cls, model_path: Path) -> None:
        """載入 FireRedVAD 權重。Phase 1 接受任意 _VadEngine 實作。"""
        from app.services.audio._firered_vad_loader import load_firered_vad  # 延遲 import

        cls._model = load_firered_vad(model_path)

    @classmethod
    def set_model(cls, model: _VadEngine | None) -> None:
        """測試用：直接注入 mock 模型。"""
        cls._model = model

    @classmethod
    async def detect_speech(cls, wav_path: Path) -> list[Segment]:
        if cls._model is None:
            raise AudioVadNotReadyError()
        try:
            raw = await asyncio.to_thread(cls._model.infer, str(wav_path))
        except Exception as e:
            raise AudioVadFailedError(details={"reason": str(e)}) from e
        segments = [Segment(start_sec=s, end_sec=e) for s, e in raw]
        if not segments:
            raise AudioNoSpeechError(details={"wav_path": str(wav_path)})
        return segments
