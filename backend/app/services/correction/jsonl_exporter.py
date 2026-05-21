"""Session 段落匯出成 JSONL（Fine-tune 訓練格式）。

每行 JSON 物件包含：text, speaker, start, end, audio_file_id。
排除：corrected_text 為 NULL、is_skipped=True 的段落。
"""
from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AudioFile, Transcription
from app.repositories.correction import CorrectionSegmentRepository, CorrectionSessionRepository


def session_to_jsonl(db: Session, session_id: int, api_key_id: int) -> str:
    """產出 JSONL 字串，每行一個段落記錄。

    空 session 或查無 session 時回傳空字串。
    """
    sess_repo = CorrectionSessionRepository(db, api_key_id)
    sess = sess_repo.get(session_id)
    if sess is None:
        return ""

    # 取 transcription → audio_file_id（供訓練資料對應音檔）
    transcription = db.get(Transcription, sess.transcription_id)
    audio_file_id: int | None = None
    if transcription is not None:
        audio = db.execute(
            select(AudioFile).where(AudioFile.transcription_id == transcription.id)
        ).scalar_one_or_none()
        if audio is not None:
            audio_file_id = audio.id

    seg_repo = CorrectionSegmentRepository(db, api_key_id)
    segs = seg_repo.list_by_session(session_id)

    lines: list[str] = []
    for seg in segs:
        if seg.is_skipped or seg.corrected_text is None:
            continue
        rec = {
            "audio_file_id": audio_file_id,
            "text": seg.corrected_text,
            "speaker": seg.speaker_label,
            "start": seg.start_sec,
            "end": seg.end_sec,
        }
        lines.append(json.dumps(rec, ensure_ascii=False))
    return "\n".join(lines)
