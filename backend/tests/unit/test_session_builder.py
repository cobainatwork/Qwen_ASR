"""_build_segments 邊界測試。"""

from __future__ import annotations

from unittest.mock import MagicMock

from app.services.correction.session_builder import _build_segments


def _make_transcription(
    timestamps: list[dict] | None,
    duration_sec: float = 0.0,
    transcript_text: str = "",
) -> MagicMock:
    """建立模擬 Transcription 物件。"""
    t = MagicMock()
    t.timestamps = timestamps
    t.duration_sec = duration_sec
    t.transcript_text = transcript_text
    return t


def test_empty_timestamps() -> None:
    """timestamps 為 None（空）→ 回傳 1 個 fallback segment（整段視為一段）。"""
    transcription = _make_transcription(timestamps=None, duration_sec=5.0, transcript_text="Hello")
    segments = _build_segments(transcription)
    assert len(segments) == 1
    assert segments[0]["text"] == "Hello"
    assert segments[0]["start_sec"] == 0.0
    assert segments[0]["end_sec"] == 5.0


def test_first_word_exceeds_threshold_no_empty_segment() -> None:
    """首個 word end > 10s 時，不應產生 text="" 的空段落。"""
    timestamps = [
        {"start": 0, "end": 11, "word": "Long"},
        {"start": 11, "end": 14, "word": "Short"},
    ]
    transcription = _make_transcription(timestamps=timestamps)
    segments = _build_segments(transcription)
    # 不應出現空段落
    assert all(s["text"] != "" for s in segments)
    # 第一個 word end=11 超過 10s，但 current_words=[] 時不應 flush（BUG-1 修正）
    # 結果應為 2 段：[0–11 "Long"] 與 [11–14 "Short"]
    assert len(segments) == 2
    assert segments[0]["text"] == "Long"
    assert segments[0]["start_sec"] == 0.0
    assert segments[0]["end_sec"] == 11.0
    assert segments[1]["text"] == "Short"
    assert segments[1]["start_sec"] == 11.0
    assert segments[1]["end_sec"] == 14.0


def test_normal_multi_segment() -> None:
    """30 個 word（每個 1 秒）應切成 3 段以上，且每段 text 非空。"""
    timestamps = [
        {"start": float(i), "end": float(i + 1), "word": f"w{i}"}
        for i in range(30)
    ]
    transcription = _make_transcription(timestamps=timestamps)
    segments = _build_segments(transcription)
    assert len(segments) >= 3
    for s in segments:
        assert s["text"] != ""
        assert s["start_sec"] >= 0.0
        assert s["end_sec"] > s["start_sec"]
