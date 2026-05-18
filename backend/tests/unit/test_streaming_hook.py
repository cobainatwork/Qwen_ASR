import pytest
from app.services.ws_quality.streaming import (
    STREAMING_SUPPORTS_BATCH,
    STREAMING_SUPPORTS_TIMESTAMPS,
    StreamingChunkResult,
    UnimplementedStreamingTranscriber,
    get_streaming_limitations,
)


def test_limitation_constants_are_false() -> None:
    """qwen-asr 0.0.6 streaming 限制不可被誤改為 True。"""
    assert STREAMING_SUPPORTS_TIMESTAMPS is False
    assert STREAMING_SUPPORTS_BATCH is False


def test_get_streaming_limitations_returns_reserved() -> None:
    info = get_streaming_limitations()
    assert info["status"] == "reserved"
    assert info["supports_timestamps"] is False
    assert info["supports_batch"] is False


@pytest.mark.asyncio
async def test_unimplemented_start_raises() -> None:
    t = UnimplementedStreamingTranscriber()
    with pytest.raises(NotImplementedError, match="Phase 3"):
        await t.start(sample_rate=16000)


@pytest.mark.asyncio
async def test_unimplemented_feed_raises() -> None:
    t = UnimplementedStreamingTranscriber()
    with pytest.raises(NotImplementedError, match="Phase 3"):
        await t.feed(pcm_chunk=b"\x00\x00")


@pytest.mark.asyncio
async def test_unimplemented_finalize_raises() -> None:
    t = UnimplementedStreamingTranscriber()
    with pytest.raises(NotImplementedError, match="Phase 3"):
        await t.finalize()


def test_streaming_chunk_result_dataclass() -> None:
    r = StreamingChunkResult(text_delta="你好", is_final=False)
    assert r.text_delta == "你好"
    assert r.is_final is False
    assert r.language is None
