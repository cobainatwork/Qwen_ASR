"""Qwen3-ForcedAligner 載入器（延遲 import，與 audio extras 一致策略）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


def load_aligner(model_path: Path) -> Any:
    """嘗試載入 Qwen3-ForcedAligner；若 import 或檔案缺失則 RuntimeError。"""
    try:
        # Qwen3-ForcedAligner 透過 transformers / torchaudio 介面載入
        # 實際 API 依官方 release，本 plan 提供延伸點。
        from transformers import AutoModel, AutoProcessor  # type: ignore[import-not-found]
    except ImportError as e:
        raise RuntimeError(
            "transformers 套件未安裝。GPU 環境請以 INSTALL_GPU_DEPS=true 重建映像。"
        ) from e

    if not model_path.exists():
        raise RuntimeError(f"Aligner 模型權重不存在：{model_path}")

    logger.info("loading Qwen3-ForcedAligner", model_path=str(model_path))
    model = AutoModel.from_pretrained(str(model_path), trust_remote_code=True)
    processor = AutoProcessor.from_pretrained(str(model_path), trust_remote_code=True)
    return {"model": model, "processor": processor}
