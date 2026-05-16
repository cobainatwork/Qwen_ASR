"""FireRedVAD 模型載入器。

實際模型載入會依 FireRedVAD repo 提供的 API。Phase 1 提供 placeholder
讓 service 結構就緒；M4 啟動 GPU 環境時補完真實載入。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


def load_firered_vad(model_path: Path) -> Any:
    """嘗試載入 FireRedVAD 模型；若 import 失敗則 raise RuntimeError。"""
    try:
        # FireRedVAD 官方倉庫尚未發 PyPI；運行環境必須將 repo 安裝為套件
        from firered_vad import FireRedVAD  # type: ignore[import-not-found]
    except ImportError as e:
        raise RuntimeError(
            "firered_vad 套件未安裝。請將 FireRedVAD 倉庫安裝為可 import 的套件。"
        ) from e

    if not model_path.exists():
        raise RuntimeError(f"VAD 模型權重不存在：{model_path}")
    logger.info("loading FireRedVAD", model_path=str(model_path))
    return FireRedVAD.load(str(model_path))
