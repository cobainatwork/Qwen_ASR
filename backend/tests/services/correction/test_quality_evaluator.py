"""Quality evaluator：對接 dataset quality service（mock contract test）。

Self-contained fixture — follows project pattern (test_correction_router.py).
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from app.services.correction.quality_evaluator import evaluate_session_quality
from sqlalchemy.orm import Session
from tests.services.correction.conftest import seed_session

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def qual_setup(db_session: Session, correction_service_setup):
    return correction_service_setup


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_evaluate_calls_dataset_quality_service(qual_setup) -> None:
    """evaluate_session_quality 應將校正文字清單傳入 evaluate_text_quality 並回傳其結果。"""
    db, api_key_id = qual_setup
    sess_id = seed_session(
        db,
        api_key_id=api_key_id,
        audio_filename="qual.wav",
        segments=[
            {"index": 0, "start": 0.0, "end": 1.0, "original": "a",
             "corrected": "A", "speaker": "S0", "skipped": False},
        ],
    )
    with patch("app.services.correction.quality_evaluator.evaluate_text_quality") as mock_fn:
        mock_fn.return_value = {"score": 0.95, "issues": []}
        result = evaluate_session_quality(db, sess_id, api_key_id=api_key_id)

    assert result["score"] == 0.95
    mock_fn.assert_called_once()
    # 校正文字「A」必須出現在傳入的 texts 清單中
    call_args = mock_fn.call_args[0]
    assert len(call_args) == 1
    assert "A" in call_args[0]
