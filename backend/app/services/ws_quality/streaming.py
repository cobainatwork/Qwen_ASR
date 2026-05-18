"""Phase 3 streaming 介面骨架（v1.10 §17.x Future Work / changelog #43）。

qwen-asr 0.0.6 streaming 限制：
1. 不支援 timestamps（streaming 模式 result.time_stamps 為 None）。
2. 不支援 batch（單連線單音流）。
3. 同步阻塞 API，必須以 asyncio.to_thread 隔離。

完整實作待規格 §3.3.x streaming API 落地。本模組僅定義抽象介面與限制
常數，使 router 可在 Phase 3 直接 import 不必重構 ws.py。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

# ─── 限制常數（暴露給 router stream.start 回應與 OpenAPI 文檔）───────────
STREAMING_SUPPORTS_TIMESTAMPS = False
STREAMING_SUPPORTS_BATCH = False
STREAMING_REQUIRES_THREAD_OFFLOAD = True


@dataclass(frozen=True)
class StreamingChunkResult:
    """單次 streaming chunk 回傳。timestamps 永遠為 None。"""

    text_delta: str
    is_final: bool
    language: str | None = None


class StreamingTranscriber(ABC):
    """Phase 3 streaming 抽象介面。Phase 2 不提供任何具體實作。"""

    @abstractmethod
    async def start(self, sample_rate: int, language: str | None = None) -> None:
        """初始化 streaming state（包裝 qwen-asr init_streaming_state）。"""

    @abstractmethod
    async def feed(self, pcm_chunk: bytes) -> StreamingChunkResult:
        """送入 PCM chunk，回傳遞增結果（包裝 streaming_transcribe）。"""

    @abstractmethod
    async def finalize(self) -> StreamingChunkResult:
        """結束 streaming session。"""


class UnimplementedStreamingTranscriber(StreamingTranscriber):
    """Phase 2 預設實作：任何方法呼叫都 raise NotImplementedError。

    存在的目的：讓 router 可以 import StreamingTranscriber 並做型別檢查，
    但實際 stream.start 時仍走 ws.py 內 stream.unavailable 回應路徑，
    不會真的呼叫到本 class 的方法。
    """

    async def start(self, sample_rate: int, language: str | None = None) -> None:
        raise NotImplementedError(
            "streaming endpoint reserved for Phase 3 (spec §3.3.x pending)"
        )

    async def feed(self, pcm_chunk: bytes) -> StreamingChunkResult:
        raise NotImplementedError(
            "streaming endpoint reserved for Phase 3 (spec §3.3.x pending)"
        )

    async def finalize(self) -> StreamingChunkResult:
        raise NotImplementedError(
            "streaming endpoint reserved for Phase 3 (spec §3.3.x pending)"
        )


def get_streaming_limitations() -> dict[str, Any]:
    """回傳 streaming 限制清單，供 router stream.start 回應與 OpenAPI 文檔使用。

    回傳結構固定，client 可以序列化解析：
    - supports_timestamps / supports_batch / requires_thread_offload: bool 旗標
    - status: 'reserved'
    - phase: 'Phase 3 (post spec §3.3.x)'
    - limitations: list[str] 給 WebSocket stream.unavailable 訊息顯示
    """
    return {
        "supports_timestamps": STREAMING_SUPPORTS_TIMESTAMPS,
        "supports_batch": STREAMING_SUPPORTS_BATCH,
        "requires_thread_offload": STREAMING_REQUIRES_THREAD_OFFLOAD,
        "status": "reserved",
        "phase": "Phase 3 (post spec §3.3.x)",
        "limitations": [
            "qwen-asr 0.0.6 streaming does not support timestamps",
            "qwen-asr 0.0.6 streaming does not support batch input",
        ],
    }
