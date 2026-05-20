"""簡體轉繁體（OpenCC s2twp，spec §6 line 437）。

spec §6.1 step 4 規定 post-processing 管線在 punctuation 之後、numbers 之前
必經一步簡繁轉換，使用 ``s2twp.json`` 設定（Simplified → Traditional Taiwan +
phrase 級詞彙轉換，例如「用户 → 使用者」、「优化 → 最佳化」）。實作以
``opencc-python-reimplemented`` 純 Python 套件提供，跨平台無 C++ build 依賴。

OpenCC 物件建立成本不可忽略（載入字典 ~50ms），module-level 單例避免每次轉換
重複 init。執行緒安全：opencc-python-reimplemented 內部 dict 為唯讀，多執行緒
read 安全；transcriber 走 ``asyncio.to_thread`` 包同步呼叫，無 race 風險。
"""

from __future__ import annotations

from opencc import OpenCC

_CONVERTER = OpenCC("s2twp")


def convert_s2twp(text: str) -> str:
    """將簡體中文轉換為臺灣繁體中文（含 phrase-level 詞彙映射）。"""
    if not text:
        return text
    return str(_CONVERTER.convert(text))
