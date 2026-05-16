"""Hotword 推理整合策略（規格 §13.2）。

三層架構：
- ShallowFusionStrategy：< 100 詞，推理時 logits 加權
- CtcWsStrategy：100-1000 詞，CTC Word Spotter
- > 1000 詞：dispatcher 層拋 HotwordTooLargeError，導向 Fine-tune
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class HotwordContext:
    """傳遞給 ASR 推理引擎的 Hotword context。

    M4 既有 Transcriber.run 未使用此 context；Phase 2 後續 milestone
    （或單獨 PR）將整合至 ASR pipeline。
    """

    group_id: int
    strategy_name: str
    words: list[str]
    weights: list[float]


class HotwordStrategy(ABC):
    """所有策略的共同介面。"""

    @abstractmethod
    def build_context(self, group_id: int, words: list[dict[str, Any]]) -> HotwordContext: ...

    @property
    @abstractmethod
    def name(self) -> str: ...


class ShallowFusionStrategy(HotwordStrategy):
    @property
    def name(self) -> str:
        return "shallow_fusion"

    def build_context(self, group_id: int, words: list[dict[str, Any]]) -> HotwordContext:
        return HotwordContext(
            group_id=group_id,
            strategy_name=self.name,
            words=[str(w["word"]) for w in words],
            weights=[float(w.get("weight", 1.0)) for w in words],
        )


class CtcWsStrategy(HotwordStrategy):
    @property
    def name(self) -> str:
        return "ctc_ws"

    def build_context(self, group_id: int, words: list[dict[str, Any]]) -> HotwordContext:
        return HotwordContext(
            group_id=group_id,
            strategy_name=self.name,
            words=[str(w["word"]) for w in words],
            weights=[float(w.get("weight", 1.0)) for w in words],
        )
