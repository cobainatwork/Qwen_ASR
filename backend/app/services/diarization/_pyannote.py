"""pyannote.audio 載入器（VRAM ~2 GB，需 HF_TOKEN）。"""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)


def load_pyannote(hf_token: str | None) -> Any:
    if not hf_token:
        raise RuntimeError("HF_TOKEN 未設定，無法載入 pyannote")
    try:
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
