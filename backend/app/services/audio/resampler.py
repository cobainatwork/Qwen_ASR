from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from app.core.exceptions import AudioDecodeTimeoutError, AudioResampleFailedError

_RESAMPLE_TIMEOUT_SEC = 30


def _require_audio_deps() -> tuple:
    """延遲載入 audio optional deps；缺少套件時拋出 RuntimeError。"""
    try:
        import soundfile as sf
        import torch
        import torchaudio.transforms as _T  # type: ignore[import-not-found]
    except ImportError as e:
        raise RuntimeError(
            "audio 套件未安裝（soundfile/torch/torchaudio）。"
            "請以 INSTALL_AUDIO_DEPS=true 重建映像。"
        ) from e
    return sf, torch, _T


@dataclass
class ResampleResult:
    output_path: Path
    original_sample_rate: int
    duration_sec: float
    resampling_warning: bool


def _load_audio(src: Path) -> tuple:
    """以 soundfile 載入音檔，回傳 (waveform: Tensor[C, T], orig_sr: int)。

    soundfile 讀取 PCM_U8 時已自動正規化為 float32 [-0.5, 0.5]；
    其餘格式正規化為 [-1.0, 1.0]。均符合後續重取樣輸入範圍。
    讀取結果為 0 個樣本時，視為損壞檔案並拋出 RuntimeError。

    工程決策：本平台音檔載入統一走 soundfile（直接綁定 libsndfile），
    刻意不使用 ``torchaudio.load``。原因：torchaudio 2.9.x 廢除自家
    backend，全部委派 torchcodec；torchcodec 0.7.0 在 slim-bookworm
    ffmpeg 5.1 環境下會於 C++ STL ``vector::reserve`` 拋 ``std::length_error``
    並終結 worker process（無 Python 例外可 catch）。soundfile 為純
    libsndfile binding，繞過 codec / torchcodec 層；qwen-asr 0.0.6
    於 host 端傳入 numpy/tensor 時亦不會落入內部 torchcodec path。
    因此 pyproject ``[audio]`` extras 故意不引入 torchcodec。
    """
    sf, torch, _T = _require_audio_deps()
    with sf.SoundFile(str(src)) as f:
        frames = f.read(dtype="float32", always_2d=True)  # shape [T, C]
    if frames.shape[0] == 0:
        raise RuntimeError("音檔不含任何可讀取的樣本（檔案損壞或格式錯誤）")
    waveform = torch.from_numpy(frames.T)  # [C, T]
    with sf.SoundFile(str(src)) as meta:
        orig_sr = meta.samplerate
    return waveform, orig_sr


async def resample_to_16k_mono(src: Path, dst_dir: Path) -> ResampleResult:
    """將任意取樣率 / 通道 / 位元深度音檔轉為 16 kHz mono 16-bit WAV。"""
    # 此函式僅用到 sf 與 _T；torch 不直接呼叫，但 _require_audio_deps()
    # 仍須觸發延遲 import，缺 audio extras 時於此 raise。
    sf, _torch, _T = _require_audio_deps()
    await asyncio.to_thread(dst_dir.mkdir, parents=True, exist_ok=True)
    try:
        async with asyncio.timeout(_RESAMPLE_TIMEOUT_SEC):
            waveform, orig_sr = await asyncio.to_thread(_load_audio, src)
    except TimeoutError as e:
        raise AudioDecodeTimeoutError(details={"src": str(src)}) from e
    except Exception as e:
        raise AudioResampleFailedError(details={"reason": str(e), "src": str(src)}) from e

    try:
        # 多通道 → mono
        if waveform.shape[0] > 1:
            waveform = waveform.mean(dim=0, keepdim=True)

        if orig_sr != 16000:
            resampler = _T.Resample(
                orig_freq=orig_sr,
                new_freq=16000,
                lowpass_filter_width=64,
                rolloff=0.9475937167092650,
            )
            waveform = resampler(waveform)
    except Exception as e:
        raise AudioResampleFailedError(details={"reason": str(e), "stage": "transform"}) from e

    out_path = dst_dir / f"{uuid4()}_16k.wav"
    try:
        await asyncio.to_thread(
            sf.write,
            str(out_path),
            waveform.squeeze().numpy(),
            16000,
            subtype="PCM_16",
        )
    except Exception as e:
        raise AudioResampleFailedError(details={"reason": str(e), "stage": "write"}) from e

    duration_sec = waveform.shape[-1] / 16000
    return ResampleResult(
        output_path=out_path,
        original_sample_rate=orig_sr,
        duration_sec=duration_sec,
        resampling_warning=(orig_sr == 8000),
    )
