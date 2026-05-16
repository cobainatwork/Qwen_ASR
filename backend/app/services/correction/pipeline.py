"""糾錯四層管線（NEC → KenLM → 同音 → LLM）。

每層獨立失敗跳過，**不阻擋辨識**（規格 §16.3）。
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import structlog

from app.services.correction.homophone import HomophoneCorrector
from app.services.correction.kenlm_corrector import KenlmCorrector
from app.services.correction.llm import LlmCorrector
from app.services.correction.nec import NecCorrector

logger = structlog.get_logger(__name__)


@dataclass
class CorrectionOptions:
    nec_enabled: bool = False
    kenlm_enabled: bool = False
    homophone_enabled: bool = False
    llm_enabled: bool = False


@dataclass
class CorrectionResult:
    final_text: str
    stages: list[dict[str, Any]] = field(default_factory=list)


async def _try_layer(
    name: str,
    func: Callable[[str], Any],
    current: str,
    stages: list[dict[str, Any]],
) -> str:
    """執行單一層，失敗跳過寫入 stages。回傳更新後的 text。"""
    try:
        if asyncio.iscoroutinefunction(func):
            result = await func(current)
        else:
            result = await asyncio.to_thread(func, current)
        stages.append({"layer": name, "status": "ok"})
        return str(result)
    except Exception as e:
        stages.append({"layer": name, "status": "failed", "error": str(e)})
        logger.warning(f"correction {name} failed", error=str(e))
        return current


async def run_correction_pipeline(text: str, options: CorrectionOptions) -> CorrectionResult:
    stages: list[dict[str, Any]] = []
    current = text

    if options.nec_enabled and NecCorrector.is_ready():
        current = await _try_layer("nec", NecCorrector.correct, current, stages)
    if options.kenlm_enabled and KenlmCorrector.is_ready():
        current = await _try_layer("kenlm", KenlmCorrector.correct, current, stages)
    if options.homophone_enabled and HomophoneCorrector.is_ready():
        current = await _try_layer("homophone", HomophoneCorrector.correct, current, stages)
    if options.llm_enabled and LlmCorrector.is_ready():
        current = await _try_layer("llm", LlmCorrector.correct, current, stages)

    return CorrectionResult(final_text=current, stages=stages)
