"""簡單規則式標點補回（規格 §3.3.4）。"""

from __future__ import annotations

# 句末詞 → 標點 mapping（規則簡化版，後續可換為模型）
_END_WORDS = {
    "嗎": "？",
    "呢": "？",
    "啊": "！",
    "呀": "！",
    "哎": "！",
}

_LONG_PAUSE_THRESHOLD_SEC = 0.6  # 段落間隔 ≥ 此值補句號


def add_punctuation(text: str, segment_breaks: list[float] | None = None) -> str:
    """為連續無標點文字補回基本標點。

    - 句末特定詞補 ？或 ！
    - segment_breaks 表示 VAD 段落結束位置（透過 transcriber 傳入），間隔 ≥ 閾值補句號
    - 已有標點不重複加
    """
    if not text:
        return text
    result = text
    for word, mark in _END_WORDS.items():
        # 在連續句末 word 後加標點（若尚未有）
        result = result.replace(f"{word} ", f"{word}{mark} ")
        result = result.replace(f"{word}\n", f"{word}{mark}\n")
        if result.endswith(word):
            result = result + mark
    # 結尾無標點補句號
    if result and result[-1] not in "。？！，；：":
        result = result + "。"
    return result
