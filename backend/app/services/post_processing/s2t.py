"""簡體轉繁體（OpenCC s2twp，spec §6 line 437）+ Taiwan 強用語補丁。

spec §6.1 step 4 規定 post-processing 管線在 punctuation 之後、numbers 之前
必經一步簡繁轉換，使用 ``s2twp.json`` 設定（Simplified → Traditional Taiwan +
phrase 級詞彙轉換，例如「用户 → 使用者」、「优化 → 最佳化」）。實作以官方
``opencc`` C++ binding 提供（PyPI package "opencc"），字典版本 1.3.x 對常見
會議/技術詞彙命中 ~89%。

OpenCC 取「兩岸通用」變體但 Taiwan 罕用的少數詞（賬號、反饋、軟盤）由
``taiwan_overrides.apply_taiwan_overrides`` 在 OpenCC 之後做純字串替換補強。

OpenCC 物件建立成本不可忽略（載入字典 ~50ms），module-level 單例避免每次轉換
重複 init。執行緒安全：OpenCC C++ binding 的 convert 為 stateless read-only
操作；transcriber 走 ``asyncio.to_thread`` 包同步呼叫，無 race 風險。
"""

from __future__ import annotations

from opencc import OpenCC

from app.services.post_processing.taiwan_overrides import apply_taiwan_overrides

_CONVERTER = OpenCC("s2twp")


def convert_s2twp(text: str) -> str:
    """將簡體中文轉換為臺灣繁體中文（含 phrase-level 詞彙映射 + Taiwan 補丁）。"""
    if not text:
        return text
    converted = str(_CONVERTER.convert(text))
    return apply_taiwan_overrides(converted)
