"""CAM++ fallback（純 CPU，精度較低但無 HF_TOKEN 依賴）。"""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)


def load_campp() -> Any:
    try:
        from modelscope.pipelines import pipeline  # type: ignore[import-not-found]
    except ImportError as e:
        raise RuntimeError("modelscope 套件未安裝") from e

    logger.info("loading CAM++ from modelscope")
    return pipeline(
        task="speaker-diarization",
        model="damo/speech_campplus_speaker-diarization_common",
    )


def run_campp(pipe: Any, wav_path: str) -> list[tuple[str, float, float]]:
    result = pipe(wav_path)
    segments: list[tuple[str, float, float]] = []
    for seg in result.get("text", []):
        segments.append((str(seg["spk"]), float(seg["start"]), float(seg["end"])))
    return segments
