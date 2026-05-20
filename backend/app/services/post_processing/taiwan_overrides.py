"""OpenCC s2twp 之後的 Taiwan 強用語補丁。

OpenCC 1.3.x s2twp 字典對 ~89% 常見會議/技術詞彙已給出 Taiwan 形式（軟體、滑鼠、
記憶體、伺服器、頻寬、最佳化、使用者、體驗 等）。少數詞 OpenCC 取了「兩岸通用」
變體（如「賬號」、「反饋」、「軟盤」），Taiwan 實際罕用，本模組對這些做
post-OpenCC 字串替換。

**Seed 原則**：只收錄 mainland → mainland-form-via-OpenCC 之後仍非 Taiwan
偏好的詞；雙方都可接受的詞（如「質量」vs「品質」）**不**強制覆寫，避免改掉
合法用法。新增條目時請確認該 mainland form 在 Taiwan 真的罕用，再加入。
"""

from __future__ import annotations

# key：OpenCC s2twp 之後仍是 mainland-leaning 的繁體形；value：Taiwan 慣用形
TAIWAN_OVERRIDES: dict[str, str] = {
    "賬號": "帳號",
    "反饋": "回饋",
    "軟盤": "軟碟",
}


def apply_taiwan_overrides(text: str) -> str:
    """套用 Taiwan 強用語映射。對每個 key 做純字串 replace。

    順序敏感性：當前條目互不重疊（key 之間沒有 prefix 關係），任意順序皆安全。
    新增有重疊風險的條目時請改用 longest-first iteration 或用 re.sub 邊界守衛。
    """
    if not text:
        return text
    for src, dst in TAIWAN_OVERRIDES.items():
        if src in text:
            text = text.replace(src, dst)
    return text
