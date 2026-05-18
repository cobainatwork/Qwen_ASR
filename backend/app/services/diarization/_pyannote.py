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


def _patch_torch_load_for_pyannote() -> None:
    """PyTorch 2.6+ 預設 ``torch.load(weights_only=True)``，會拒絕 pyannote 3.4
    checkpoint 中的 ``torch.torch_version.TorchVersion`` 等 non-tensor 物件，
    拋 ``_pickle.UnpicklingError``。

    解法：將 ``torch.load`` 預設 ``weights_only`` 改為 ``False``。pyannote
    checkpoint 來自 huggingface.co/pyannote/speaker-diarization-3.1（trusted
    upstream + 需 HF terms accept），符合 PyTorch 文件「trusted source」豁免
    條件。Monkey-patch 限 process 生命週期；本專案啟動完成後不再有其他
    ``torch.load`` 呼叫（vllm 用自家 loader、resampler 用 soundfile），無副作用。
    """
    import torch

    if getattr(torch.load, "_pyannote_weights_only_patched", False):
        return
    _orig_load = torch.load

    def _safe_load(*args: Any, **kwargs: Any) -> Any:
        kwargs.setdefault("weights_only", False)
        return _orig_load(*args, **kwargs)

    _safe_load._pyannote_weights_only_patched = True  # type: ignore[attr-defined]
    torch.load = _safe_load  # type: ignore[assignment]


def load_pyannote(hf_token: str | None) -> Any:
    if not hf_token:
        raise RuntimeError("HF_TOKEN 未設定，無法載入 pyannote")
    try:
        _patch_torchaudio_for_pyannote()
        _patch_torch_load_for_pyannote()
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
