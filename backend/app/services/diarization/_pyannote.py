"""pyannote.audio 載入器（VRAM ~2 GB，需 HF_TOKEN）。"""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)


def _patch_torchaudio_for_pyannote() -> None:
    """torchaudio 2.4+ 移除 ``AudioMetaData`` 與 ``list_audio_backends``，
    但 pyannote.audio 3.x 仍引用兩者；不打 shim 就會在 ``import pyannote.audio``
    階段 ``AttributeError`` 直接 crash。

    Upstream wontfix issue: https://github.com/pyannote/pyannote-audio/issues/1952
    pyannote 4.x 改用 torchcodec，但本專案 slim-bookworm + ffmpeg 5.1 環境已知
    torchcodec C++ STL crash，故鎖 3.x + shim 是當前最穩路徑（移除條件：upstream
    釋出 3.x 相容修補版，或本專案 base image 更換可乾淨跑 torchcodec）。
    """
    import torchaudio

    if not hasattr(torchaudio, "AudioMetaData"):
        torchaudio.AudioMetaData = object  # type: ignore[attr-defined]
    if not hasattr(torchaudio, "list_audio_backends"):
        torchaudio.list_audio_backends = lambda: ["soundfile"]  # type: ignore[attr-defined]


def load_pyannote(hf_token: str | None) -> Any:
    if not hf_token:
        raise RuntimeError("HF_TOKEN 未設定，無法載入 pyannote")
    try:
        _patch_torchaudio_for_pyannote()
        from pyannote.audio import Pipeline  # type: ignore[import-not-found]
    except ImportError as e:
        raise RuntimeError("pyannote.audio 套件未安裝") from e

    logger.info("loading pyannote.audio speaker diarization pipeline")
    return Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1",
        use_auth_token=hf_token,
    )


def run_pyannote(pipeline: Any, wav_path: str) -> list[tuple[str, float, float]]:
    """執行 pyannote diarization，回傳 list[(speaker_id, start_sec, end_sec)]。"""
    diarization = pipeline(wav_path)
    segments: list[tuple[str, float, float]] = []
    for turn, _, speaker in diarization.itertracks(yield_label=True):
        segments.append((str(speaker), float(turn.start), float(turn.end)))
    return segments
