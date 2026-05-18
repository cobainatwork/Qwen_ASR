"""FireRedVAD 模型載入器（PyPI ``fireredvad>=0.0.2``）。

PyPI 上的官方套件名為 ``fireredvad``（v1.10 §3.3.3：原誤記 ``firered_vad`` 已更正）。
``FireRedVad.from_pretrained(model_dir, config)`` 接受一個包含 ``cmvn.ark`` 與
DetectModel 權重的本地目錄；模型權重需事先從 FireRedTeam 官方倉庫
（https://github.com/FireRedTeam/FireRedVAD）的 ``pretrained_models/FireRedVAD/VAD``
子目錄取得，部署時掛入 ``$VAD_MODEL_DIR``（預設 ``/data/models/FireRedVAD``）。

對 ``FireRedVADService`` 暴露的介面為 ``_VadEngine`` Protocol：
``infer(wav_path: str) -> list[tuple[float, float]]``。本載入器以 adapter 包裹
官方 ``FireRedVad.detect(audio) -> ({"dur", "timestamps", "wav_path"?}, probs)``
回傳值，僅取出 ``timestamps`` 給上層 service。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class _FireRedAdapter:
    """將 fireredvad ``FireRedVad.detect`` 包成 ``_VadEngine.infer`` 介面。"""

    def __init__(self, model: Any) -> None:
        self._model = model

    def infer(self, wav_path: str) -> list[tuple[float, float]]:
        result, _probs = self._model.detect(wav_path, do_postprocess=True)
        timestamps = result.get("timestamps") or []
        return [(float(start), float(end)) for start, end in timestamps]


def load_firered_vad(model_dir: Path) -> _FireRedAdapter:
    """嘗試載入 FireRedVAD 模型；若 import 或 model_dir 不可用則 raise RuntimeError。

    ``model_dir`` 需包含 fireredvad 預期的 ``cmvn.ark`` 與 DetectModel 權重檔；
    詳見 FireRedTeam 倉庫的 ``pretrained_models/FireRedVAD/VAD`` 範例。
    """
    try:
        from fireredvad import FireRedVad, FireRedVadConfig
    except ImportError as e:
        raise RuntimeError(
            "fireredvad 套件未安裝。請以 `pip install fireredvad>=0.0.2,<0.1` 或"
            " `INSTALL_AUDIO_DEPS=true` 容器重建。"
        ) from e

    if not model_dir.is_dir():
        raise RuntimeError(
            f"VAD 模型目錄不存在或非目錄：{model_dir}。"
            f"請從 https://github.com/FireRedTeam/FireRedVAD 取得 pretrained_models/FireRedVAD/VAD"
            f" 內容並掛入該路徑。"
        )

    logger.info("loading FireRedVAD", model_dir=str(model_dir))
    # fireredvad 0.0.2 的 use_gpu=False 為 CPU path；0.6M 參數推理足夠快，預設保留
    # CPU 以避免與主 ASR 引擎共用 cuda:0；若日後要切換 GPU 再加 VAD_USE_GPU 設定。
    config = FireRedVadConfig(use_gpu=False)
    real_model = FireRedVad.from_pretrained(str(model_dir), config=config)
    return _FireRedAdapter(real_model)
