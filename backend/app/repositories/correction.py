from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import CorrectionVersionMismatchError
from app.models import CorrectionSegment, CorrectionSession
from app.repositories.base import TenantScopedRepository


class CorrectionSessionRepository(TenantScopedRepository[CorrectionSession]):
    """校正 Session 的租戶隔離存取層。"""

    model = CorrectionSession


class CorrectionSegmentRepository:
    """段落跨 session 存取（Tenant 透過 session → api_key_id 驗證）。

    correction_segments 表無 api_key_id 欄位，
    租戶隔離由上層 session 驗證後保證。
    """

    def __init__(self, db: Session, api_key_id: int) -> None:
        self.db = db
        self.api_key_id = api_key_id

    def list_by_session(self, session_id: int) -> list[CorrectionSegment]:
        """列出 session 下全部段落，依 segment_index 排序。"""
        return list(
            self.db.execute(
                select(CorrectionSegment)
                .where(CorrectionSegment.session_id == session_id)
                .order_by(CorrectionSegment.segment_index)
            )
            .scalars()
            .all()
        )

    def bulk_create(self, session_id: int, segments: list[dict[str, Any]]) -> int:
        """批量建立段落，自動編 segment_index。回傳新增數量。"""
        for i, seg in enumerate(segments):
            self.db.add(
                CorrectionSegment(
                    session_id=session_id,
                    segment_index=i,
                    start_sec=seg["start_sec"],
                    end_sec=seg["end_sec"],
                    original_text=seg["text"],
                )
            )
        self.db.flush()
        return len(segments)

    def get(self, segment_id: int) -> CorrectionSegment | None:
        """依 ID 取單一段落（無 tenant filter，由呼叫層驗證 session 所有權）。"""
        return self.db.execute(
            select(CorrectionSegment).where(CorrectionSegment.id == segment_id)
        ).scalar_one_or_none()

    def update_with_version(
        self,
        segment_id: int,
        *,
        expected_version: int,
        corrected_text: str,
    ) -> CorrectionSegment:
        """Optimistic Locking 更新段落校正文字。

        版本不符時拋 CorrectionVersionMismatchError，
        details 包含 expected_version / actual_version 供前端判斷。

        限制：採 read → check → write 模式（無 SELECT FOR UPDATE）。
        高並發場景可能有 race（V2 補強）。
        """
        seg = self.get(segment_id)
        if seg is None:
            raise CorrectionVersionMismatchError(
                details={"segment_id": segment_id, "reason": "not_found"}
            )
        if seg.version != expected_version:
            raise CorrectionVersionMismatchError(
                details={
                    "segment_id": segment_id,
                    "expected_version": expected_version,
                    "actual_version": seg.version,
                },
            )
        seg.corrected_text = corrected_text
        seg.version = seg.version + 1
        self.db.flush()
        return seg
