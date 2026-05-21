"""Excel 匯出：xlsx 7 欄，含 skipped / NULL corrected_text 段落。

Self-contained fixture — follows project pattern (test_correction_router.py).
"""
from __future__ import annotations

import io

import pytest
from app.services.correction.excel_exporter import session_to_excel_bytes
from openpyxl import load_workbook
from sqlalchemy.orm import Session
from tests.services.correction.conftest import seed_session

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def excel_setup(db_session: Session, correction_service_setup):
    return correction_service_setup


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_session_to_excel_columns_and_rows(excel_setup) -> None:
    """7 欄表頭正確；所有段落均輸出（含 skipped / NULL corrected）；speaker NULL → 空字串。"""
    db, api_key_id = excel_setup
    sess_id = seed_session(
        db,
        api_key_id=api_key_id,
        audio_filename="excel.wav",
        segments=[
            {"index": 0, "start": 0.0, "end": 1.5, "original": "原文 A",
             "corrected": "校正 A", "speaker": "S0", "skipped": False},
            {"index": 1, "start": 1.5, "end": 3.0, "original": "原文 B",
             "corrected": "校正 B", "speaker": None, "skipped": False},
            {"index": 2, "start": 3.0, "end": 4.0, "original": "原文 C",
             "corrected": None, "speaker": "S1", "skipped": True},
        ],
    )
    raw = session_to_excel_bytes(db, sess_id, api_key_id=api_key_id)
    wb = load_workbook(io.BytesIO(raw))
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    # 第一列 = 表頭
    assert rows[0] == ("段落", "開始", "結束", "語者", "原文", "校正", "已跳過")
    # 共 3 段 + 1 表頭
    assert len(rows) == 1 + 3
    # 第 2 段 speaker_label NULL → 空字串（openpyxl values_only=True 回傳空儲存格為 None）
    assert rows[2][3] in (None, "")
    # 第 3 段 is_skipped = True
    assert rows[3][6] is True
