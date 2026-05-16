"""從 Transcription 自動建立 CorrectionSession 與 segments。"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import Transcription
from app.repositories.correction import (
    CorrectionSegmentRepository,
    CorrectionSessionRepository,
)

_SEGMENT_DURATION_SEC = 10.0


def build_session_from_transcription(
    *,
    db: Session,
    api_key_id: int,
    transcription: Transcription,
    name: str | None = None,
) -> int:
    """建立 CorrectionSession + 依 timestamps 切段，回傳 session_id。

    切段規則：
    - 有 word-level timestamps：每 10 秒切一段。
    - 無 timestamps（M7 對齊失敗或短音檔）：整段視為一個 segment。
    """
    session_repo = CorrectionSessionRepository(db, api_key_id)
    session = session_repo.create(
        transcription_id=transcription.id,
        name=name or f"session-{transcription.id}",
    )

    segments_input = _build_segments(transcription)

    seg_repo = CorrectionSegmentRepository(db, api_key_id)
    seg_repo.bulk_create(session.id, segments_input)
    return session.id


def _build_segments(transcription: Transcription) -> list[dict[str, Any]]:
    """從 timestamps 合併為段落列表，每 10 秒切一段。"""
    if not transcription.timestamps:
        return [
            {
                "start_sec": 0.0,
                "end_sec": transcription.duration_sec or 0.0,
                "text": transcription.transcript_text or "",
            }
        ]

    segments: list[dict[str, Any]] = []
    current_start: float | None = None
    current_end: float = 0.0
    current_words: list[str] = []

    for ts in transcription.timestamps:
        start = float(ts.get("start", 0))
        end = float(ts.get("end", start))
        word = str(ts.get("word", ""))

        if current_start is None:
            current_start = start

        if current_words and end - current_start > _SEGMENT_DURATION_SEC:
            segments.append(
                {
                    "start_sec": current_start,
                    "end_sec": current_end,
                    "text": "".join(current_words),
                }
            )
            current_start = start
            current_words = []

        current_words.append(word)
        current_end = end

    if current_words and current_start is not None:
        segments.append(
            {
                "start_sec": current_start,
                "end_sec": current_end,
                "text": "".join(current_words),
            }
        )

    return segments
