"""中文數字 → 半形數字正規化。"""

from __future__ import annotations

import re

_CN_DIGITS = {
    "零": 0, "〇": 0,
    "一": 1, "二": 2, "兩": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
}

_CN_UNITS = {"十": 10, "百": 100, "千": 1000}


def _convert_segment(cn: str) -> str:
    """單一連續中文數字串轉半形。例：「一百二十三」→「123」、「兩千」→「2000」。"""
    if all(ch in _CN_DIGITS for ch in cn):
        return "".join(str(_CN_DIGITS[ch]) for ch in cn)

    total = 0
    current = 0
    for ch in cn:
        if ch in _CN_DIGITS:
            current = _CN_DIGITS[ch]
        elif ch in _CN_UNITS:
            if current == 0:
                current = 1
            total += current * _CN_UNITS[ch]
            current = 0
    total += current
    return str(total) if total > 0 else cn


_CN_NUMBER_RE = re.compile(r"[零〇一二三四五六七八九兩十百千]+")


def normalize_numbers(text: str) -> str:
    """將文字中所有連續中文數字串轉換為半形數字。"""
    return _CN_NUMBER_RE.sub(lambda m: _convert_segment(m.group(0)), text)
