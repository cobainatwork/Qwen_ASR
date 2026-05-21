"""Dataset text quality evaluator — stub for M1.3.

Full implementation deferred to Phase A4 when the dataset quality pipeline is built.
This stub satisfies the contract expected by quality_evaluator.py:
  evaluate_text_quality(texts: list[str]) -> dict
  -> {"score": float, "issues": list[{"code": str, "message": str | None}]}
"""
from __future__ import annotations

from typing import Any


def evaluate_text_quality(texts: list[str]) -> dict[str, Any]:
    """評估文字品質（stub 實作）。

    Phase A4 補強：接入真實 KenLM / NEC 評分管線。
    目前回傳固定佔位結果，不影響 API 合約。
    """
    return {
        "score": 0.0,
        "issues": [
            {
                "code": "NOT_IMPLEMENTED",
                "message": "dataset quality service stub — full impl in Phase A4",
            }
        ],
    }
