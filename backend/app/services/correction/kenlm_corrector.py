"""L2 KenLM n-gram 語言模型糾錯（純 CPU）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any


class KenlmCorrector:
    _model: Any = None

    @classmethod
    def load(cls, model_path: Path) -> None:
        try:
            import kenlm  # type: ignore[import-not-found]
        except ImportError as e:
            raise RuntimeError("kenlm 套件未安裝") from e
        if not model_path.exists():
            raise RuntimeError(f"KenLM 模型不存在：{model_path}")
        cls._model = kenlm.Model(str(model_path))

    @classmethod
    def set_model_for_test(cls, model: Any) -> None:
        cls._model = model

    @classmethod
    def is_ready(cls) -> bool:
        return cls._model is not None

    @classmethod
    def correct(cls, text: str) -> str:
        """以 5-gram score 重排候選字（占位實作）。

        實際 KenLM 整合需 candidate generator；本占位回傳原文。
        測試時透過 set_model_for_test 注入。
        """
        if cls._model is None:
            raise RuntimeError("KenLM 未載入")
        # 真實實作：對 ASR n-best list 排序，本 milestone 透過 mock 驗證介面
        if hasattr(cls._model, "correct"):
            return str(cls._model.correct(text))
        return text
