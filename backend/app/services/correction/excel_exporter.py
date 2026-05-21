"""Session → xlsx bytes（openpyxl）。

7 欄：段落 / 開始 / 結束 / 語者 / 原文 / 校正 / 已跳過。
所有段落均輸出（含 skipped / NULL corrected_text），由使用者決定如何使用。
"""
from __future__ import annotations

import io

from openpyxl import Workbook
from sqlalchemy.orm import Session

from app.repositories.correction import CorrectionSegmentRepository, CorrectionSessionRepository


def session_to_excel_bytes(db: Session, session_id: int, api_key_id: int) -> bytes:
    """產出 xlsx bytes；查無 session 時回傳空 bytes。"""
    sess_repo = CorrectionSessionRepository(db, api_key_id)
    sess = sess_repo.get(session_id)
    if sess is None:
        return b""

    seg_repo = CorrectionSegmentRepository(db, api_key_id)
    segs = seg_repo.list_by_session(session_id)

    wb = Workbook()
    ws = wb.active
    ws.title = "校正結果"
    ws.append(("段落", "開始", "結束", "語者", "原文", "校正", "已跳過"))
    for seg in segs:
        ws.append((
            seg.segment_index,
            seg.start_sec,
            seg.end_sec,
            seg.speaker_label or "",
            seg.original_text,
            seg.corrected_text or "",
            seg.is_skipped,
        ))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
