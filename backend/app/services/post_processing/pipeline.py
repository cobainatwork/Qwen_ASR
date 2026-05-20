"""後處理編排：punctuation → s2t → numbers（spec §6.1）。

spec §6 line 440 明定數字轉換必須排在簡繁轉換之後，確保簡體數字「五」先
轉繁體再被數字正規化。失敗時跳過寫入結構化結果。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog

from app.services.post_processing.numbers import normalize_numbers
from app.services.post_processing.punctuation import add_punctuation
from app.services.post_processing.s2t import convert_s2twp

logger = structlog.get_logger(__name__)


@dataclass
class PostProcessingResult:
    final_text: str
    stages: list[dict[str, Any]]


def run_post_processing(
    text: str,
    *,
    punctuation: bool = True,
    s2t: bool = True,
    numbers: bool = True,
) -> PostProcessingResult:
    """依序執行後處理階段。每階段失敗跳過並記錄。"""
    stages: list[dict[str, Any]] = []
    current = text

    if punctuation:
        try:
            current = add_punctuation(current)
            stages.append({"stage": "punctuation", "status": "ok"})
        except Exception as e:
            stages.append({"stage": "punctuation", "status": "failed", "error": str(e)})
            logger.warning("post_processing punctuation failed", error=str(e))

    if s2t:
        try:
            current = convert_s2twp(current)
            stages.append({"stage": "s2t", "status": "ok"})
        except Exception as e:
            stages.append({"stage": "s2t", "status": "failed", "error": str(e)})
            logger.warning("post_processing s2t failed", error=str(e))

    if numbers:
        try:
            current = normalize_numbers(current)
            stages.append({"stage": "numbers", "status": "ok"})
        except Exception as e:
            stages.append({"stage": "numbers", "status": "failed", "error": str(e)})
            logger.warning("post_processing numbers failed", error=str(e))

    return PostProcessingResult(final_text=current, stages=stages)
