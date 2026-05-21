"""Session 品質評估 — 對接 dataset quality service。

呼叫 evaluate_text_quality(texts) 取得分數與問題清單。
若 session 不存在或無已校正段落，回傳固定錯誤回應（不拋例外）。
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.repositories.correction import CorrectionSegmentRepository, CorrectionSessionRepository
from app.services.dataset.quality import evaluate_text_quality


def evaluate_session_quality(db: Session, session_id: int, api_key_id: int) -> dict:  # type: ignore[type-arg]
    """評估 session 的校正品質。

    回傳格式：{"score": float, "issues": list[{"code": str, "message": str | None}]}
    """
    sess_repo = CorrectionSessionRepository(db, api_key_id)
    sess = sess_repo.get(session_id)
    if sess is None:
        return {"score": 0.0, "issues": [{"code": "SESSION_NOT_FOUND", "message": None}]}

    seg_repo = CorrectionSegmentRepository(db, api_key_id)
    segs = seg_repo.list_by_session(session_id)
    texts = [s.corrected_text for s in segs if s.corrected_text and not s.is_skipped]
    if not texts:
        return {"score": 0.0, "issues": [{"code": "EMPTY_SESSION", "message": None}]}

    return evaluate_text_quality(texts)
