"""L1 命名實體糾錯（Generative-Annotation-NEC）占位介面。

實際模型載入需 GPU，本 milestone 提供結構與測試 mock 入口。
"""

from __future__ import annotations

import asyncio
from typing import Any


class NecCorrector:
    _model: Any = None

    @classmethod
    def set_model_for_test(cls, model: Any) -> None:
        cls._model = model

    @classmethod
    def is_ready(cls) -> bool:
        return cls._model is not None

    @classmethod
    async def correct(cls, text: str) -> str:
        if cls._model is None:
            raise RuntimeError("NEC 模型未載入")
        return await asyncio.to_thread(cls._model.correct, text)
