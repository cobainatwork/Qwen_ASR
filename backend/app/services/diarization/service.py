"""DiarizationService 切換 pyannote / CAM++。

Fine-tune 啟動時自動強制降級 CAM++（規格 §18.2，跨檔案決策）。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import structlog

from app.core.config import Settings
from app.core.exceptions import DiarizationFailedError, DiarizationNotReadyError
from app.services.finetune.lock import is_finetune_active

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class SpeakerSegment:
    speaker: str
    start_sec: float
    end_sec: float


class _DiarizationBackend(Protocol):
    def run(self, wav_path: str) -> list[tuple[str, float, float]]: ...

    @property
    def name(self) -> str: ...


class DiarizationService:
    _pyannote: Any = None
    _campp: Any = None
    _settings: Settings | None = None

    @classmethod
    def load(cls, settings: Settings) -> None:
        cls._settings = settings
        if settings.DIARIZATION_BACKEND == "pyannote":
            from app.services.diarization._pyannote import load_pyannote

            cls._pyannote = load_pyannote(settings.HF_TOKEN)
        else:
            from app.services.diarization._campp import load_campp

            cls._campp = load_campp()
        logger.info("DiarizationService loaded", backend=settings.DIARIZATION_BACKEND)

    @classmethod
    def set_backends_for_test(
        cls,
        pyannote: Any = None,
        campp: Any = None,
        settings: Settings | None = None,
    ) -> None:
        cls._pyannote = pyannote
        cls._campp = campp
        cls._settings = settings

    @classmethod
    async def diarize(cls, wav_path: Path) -> tuple[list[SpeakerSegment], str]:
        """回傳 (segments, backend_used)。

        Fine-tune 啟動時強制使用 CAM++（規格 §18.2）；
        若 CAM++ 也未載入則拋 DiarizationNotReadyError。
        """
        if cls._settings is None:
            raise DiarizationNotReadyError(message="DiarizationService.load 未呼叫")

        force_campp = is_finetune_active(cls._settings)
        backend_name: str

        if force_campp or cls._settings.DIARIZATION_BACKEND == "campp":
            if cls._campp is None:
                raise DiarizationNotReadyError(message="CAM++ 未載入")
            from app.services.diarization._campp import run_campp

            try:
                raw = await asyncio.to_thread(run_campp, cls._campp, str(wav_path))
            except Exception as e:
                raise DiarizationFailedError(details={"backend": "campp", "error": str(e)}) from e
            backend_name = "campp"
        else:
            if cls._pyannote is None:
                raise DiarizationNotReadyError(message="pyannote 未載入")
            from app.services.diarization._pyannote import run_pyannote

            try:
                raw = await asyncio.to_thread(run_pyannote, cls._pyannote, str(wav_path))
            except Exception as e:
                raise DiarizationFailedError(
                    details={"backend": "pyannote", "error": str(e)}
                ) from e
            backend_name = "pyannote"

        segments = [SpeakerSegment(speaker=s, start_sec=a, end_sec=b) for s, a, b in raw]
        return segments, backend_name
