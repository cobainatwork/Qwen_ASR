from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.exceptions import CorrectionSessionNotFoundError
from app.core.response import success
from app.deps.auth import require_scope
from app.deps.db import get_db
from app.models import ApiKey, CorrectionSegment, CorrectionSession
from app.repositories.correction import (
    CorrectionSegmentRepository,
    CorrectionSessionRepository,
)
from app.schemas.common import ResponseEnvelope
from app.schemas.correction import (
    CorrectionSegmentData,
    CorrectionSegmentUpdate,
    CorrectionSessionData,
    ExportToDatasetData,
    ExportToDatasetRequest,
)
from app.services.correction.exporter import export_session_to_dataset

router = APIRouter(prefix="/api/v1/correction", tags=["correction"])


def _to_session(s: CorrectionSession) -> CorrectionSessionData:
    return CorrectionSessionData(
        id=s.id,
        transcription_id=s.transcription_id,
        name=s.name,
        status=s.status,
        created_at=s.created_at,
        updated_at=s.updated_at,
    )


def _to_segment(seg: CorrectionSegment) -> CorrectionSegmentData:
    return CorrectionSegmentData(
        id=seg.id,
        session_id=seg.session_id,
        segment_index=seg.segment_index,
        start_sec=seg.start_sec,
        end_sec=seg.end_sec,
        original_text=seg.original_text,
        corrected_text=seg.corrected_text,
        speaker_label=seg.speaker_label,
        is_skipped=seg.is_skipped,
        version=seg.version,
        updated_at=seg.updated_at,
    )


@router.get("/sessions/{session_id}", response_model=ResponseEnvelope[CorrectionSessionData])
def get_session(
    session_id: int,
    api_key: ApiKey = Depends(require_scope("asr:read")),
    db: Session = Depends(get_db),
) -> ResponseEnvelope[CorrectionSessionData]:
    repo = CorrectionSessionRepository(db, api_key.id)
    sess = repo.get(session_id)
    if sess is None:
        raise CorrectionSessionNotFoundError(details={"session_id": session_id})
    return success(_to_session(sess))


@router.get(
    "/sessions/{session_id}/segments",
    response_model=ResponseEnvelope[list[CorrectionSegmentData]],
)
def list_segments(
    session_id: int,
    api_key: ApiKey = Depends(require_scope("asr:read")),
    db: Session = Depends(get_db),
) -> ResponseEnvelope[list[CorrectionSegmentData]]:
    sess_repo = CorrectionSessionRepository(db, api_key.id)
    sess = sess_repo.get(session_id)
    if sess is None:
        raise CorrectionSessionNotFoundError(details={"session_id": session_id})
    seg_repo = CorrectionSegmentRepository(db, api_key.id)
    segments = seg_repo.list_by_session(session_id)
    return success([_to_segment(s) for s in segments])


@router.put(
    "/sessions/{session_id}/segments/{segment_id}",
    response_model=ResponseEnvelope[CorrectionSegmentData],
)
def update_segment(
    session_id: int,
    segment_id: int,
    payload: CorrectionSegmentUpdate,
    api_key: ApiKey = Depends(require_scope("asr:write")),
    db: Session = Depends(get_db),
) -> ResponseEnvelope[CorrectionSegmentData]:
    # 驗證 session 屬於本 tenant
    sess_repo = CorrectionSessionRepository(db, api_key.id)
    sess = sess_repo.get(session_id)
    if sess is None:
        raise CorrectionSessionNotFoundError(details={"session_id": session_id})

    seg_repo = CorrectionSegmentRepository(db, api_key.id)
    # 驗證 segment 屬於本 session，避免同 tenant 內跨 session 越權
    existing = seg_repo.get(segment_id)
    if existing is None or existing.session_id != session_id:
        raise CorrectionSessionNotFoundError(
            details={
                "session_id": session_id,
                "segment_id": segment_id,
                "reason": "segment_not_in_session",
            },
        )

    updated = seg_repo.update_with_version(
        segment_id,
        expected_version=payload.expected_version,
        corrected_text=payload.corrected_text,
        is_skipped=payload.is_skipped,
    )
    db.commit()
    return success(_to_segment(updated))


@router.post(
    "/sessions/{session_id}/export-to-dataset",
    response_model=ResponseEnvelope[ExportToDatasetData],
)
def export_to_dataset(
    session_id: int,
    payload: ExportToDatasetRequest,
    api_key: ApiKey = Depends(require_scope("asr:write")),
    db: Session = Depends(get_db),
) -> ResponseEnvelope[ExportToDatasetData]:
    inserted = export_session_to_dataset(
        db=db,
        api_key_id=api_key.id,
        session_id=session_id,
        dataset_id=payload.dataset_id,
    )
    db.commit()
    return success(ExportToDatasetData(inserted_count=inserted, dataset_id=payload.dataset_id))
