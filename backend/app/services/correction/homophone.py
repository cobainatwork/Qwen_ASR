"""L3 同音異字糾錯（pypinyin 對照）。"""

from __future__ import annotations

# 簡化同音對照表：{錯字: 正確字}（實際應由詞典驅動）
_HOMOPHONE_MAP = {
    "在": "再",
    "他": "她",
}


class HomophoneCorrector:
    _enabled: bool = False
    _custom_map: dict[str, str] | None = None

    @classmethod
    def configure(cls, enabled: bool, custom_map: dict[str, str] | None = None) -> None:
        cls._enabled = enabled
        cls._custom_map = custom_map

    @classmethod
    def is_ready(cls) -> bool:
        return cls._enabled

    @classmethod
    def correct(cls, text: str) -> str:
        """簡化版：直接對照表替換。實際應結合上下文。"""
        if not cls._enabled:
            raise RuntimeError("Homophone corrector 未啟用")
        mapping = cls._custom_map if cls._custom_map is not None else _HOMOPHONE_MAP
        result = text
        for wrong, right in mapping.items():
            result = result.replace(wrong, right)
        return result
