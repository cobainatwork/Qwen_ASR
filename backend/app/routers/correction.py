from __future__ import annotations

import math
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import CorrectionSessionNotFoundError, TranscriptionNotFoundError
from app.core.response import success
from app.deps.auth import require_scope
from app.deps.db import get_db
from app.models import ApiKey, CorrectionSegment, CorrectionSession
from app.models.audio_file import AudioFile
from app.models.transcription import Transcription
from app.repositories.correction import (
    CorrectionSegmentRepository,
    CorrectionSessionRepository,
)
from app.repositories.transcription import TranscriptionRepository
from app.schemas.common import PaginationMeta, ResponseEnvelope
from app.schemas.correction import (
    CorrectionSegmentData,
    CorrectionSegmentUpdate,
    CorrectionSessionData,
    CorrectionSessionListData,
    CreateCorrectionSessionRequest,
    ExportToDatasetData,
    ExportToDatasetRequest,
    QualityEvalData,
)
from app.services.correction.excel_exporter import session_to_excel_bytes
from app.services.correction.exporter import export_session_to_dataset
from app.services.correction.jsonl_exporter import session_to_jsonl
from app.services.correction.quality_evaluator import evaluate_session_quality

router = APIRouter(prefix="/api/v1/correction", tags=["correction"])


def _get_audio_file_id(db: Session, transcription_id: int, api_key_id: int) -> int | None:
    """Fetch the audio_file.id whose transcription_id matches the given transcription.

    Scoped to tenant (api_key_id) to prevent cross-tenant data leakage.
    Returns None when no matching AudioFile exists.
    """
    row = db.execute(
        select(AudioFile.id)
        .where(AudioFile.transcription_id == transcription_id)
        .where(AudioFile.api_key_id == api_key_id)
        .limit(1)
    ).scalar_one_or_none()
    return row


def _to_session(s: CorrectionSession, db: Session, api_key_id: int) -> CorrectionSessionData:
    audio_file_id = _get_audio_file_id(db, s.transcription_id, api_key_id)
    return CorrectionSessionData(
        id=s.id,
        transcription_id=s.transcription_id,
        audio_file_id=audio_file_id,
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


def _build_segments_from_transcription(
    transcription: Transcription,
) -> list[dict[str, Any]]:
    """Decompose transcription JSONB into segment dicts for bulk_create.

    Strategy:
    - If `speakers` is non-empty: for each speaker turn {speaker, start, end},
      collect all word-level timestamps whose start falls in [turn.start, turn.end),
      concatenate their `text` fields, use turn timing for start_sec/end_sec,
      and carry the speaker label.
    - If `speakers` is empty/None: produce one segment spanning the entire
      transcription, using `transcript_text` as `text`.
    """
    speakers: list[dict[str, Any]] = transcription.speakers or []
    timestamps: list[dict[str, Any]] = transcription.timestamps or []
    full_text: str = transcription.transcript_text or ""

    if not speakers:
        duration = transcription.duration_sec or 0.0
        return [
            {
                "start_sec": 0.0,
                "end_sec": duration,
                "text": full_text,
            }
        ]

    segments: list[dict[str, Any]] = []
    for turn in speakers:
        t_start: float = float(turn.get("start", 0.0))
        t_end: float = float(turn.get("end", t_start))
        speaker: str = str(turn.get("speaker", ""))

        words_in_turn = [
            w["text"]
            for w in timestamps
            if float(w.get("start", 0.0)) >= t_start
            and float(w.get("start", 0.0)) < t_end
            and w.get("text")
        ]
        text = "".join(words_in_turn) if words_in_turn else ""

        segments.append(
            {
                "start_sec": t_start,
                "end_sec": t_end,
                "text": text,
                "speaker_label": speaker if speaker else None,
            }
        )
    return segments


@router.post("/sessions", response_model=ResponseEnvelope[CorrectionSessionData])
def create_session(
    payload: CreateCorrectionSessionRequest,
    api_key: ApiKey = Depends(require_scope("asr:write")),
    db: Session = Depends(get_db),
) -> ResponseEnvelope[CorrectionSessionData]:
    """從現有 transcription 建立 correction session（idempotent）。

    若該 transcription 已有 correction_session，直接回傳既有 session。
    Transcription 的 speakers + timestamps JSONB 拆成 CorrectionSegment 列表。
    """
    # 1. 驗證 transcription 屬於本 tenant
    tx_repo = TranscriptionRepository(db, api_key.id)
    transcription = tx_repo.get(payload.transcription_id)
    if transcription is None:
        raise TranscriptionNotFoundError(details={"transcription_id": payload.transcription_id})

    # 2. Idempotency：若已存在 session，直接回傳
    existing_sess = db.execute(
        select(CorrectionSession).where(
            CorrectionSession.transcription_id == payload.transcription_id,
            CorrectionSession.api_key_id == api_key.id,
        )
    ).scalar_one_or_none()
    if existing_sess is not None:
        return success(_to_session(existing_sess, db, api_key.id))

    # 3. 決定 session 名稱
    if payload.name:
        session_name = payload.name
    else:
        audio_file_id = _get_audio_file_id(db, payload.transcription_id, api_key.id)
        if audio_file_id is not None:
            af = db.get(AudioFile, audio_file_id)
            af_name = af.original_name if af and af.original_name else None
            session_name = af_name or f"轉錄 #{payload.transcription_id}"
        else:
            session_name = transcription.file_name or f"轉錄 #{payload.transcription_id}"

    # 4. 建立 CorrectionSession
    sess = CorrectionSession(
        api_key_id=api_key.id,
        transcription_id=payload.transcription_id,
        name=session_name,
        status="in_progress",
    )
    db.add(sess)
    db.flush()

    # 5. 拆 segments
    segments_data = _build_segments_from_transcription(transcription)
    seg_repo = CorrectionSegmentRepository(db, api_key.id)
    seg_repo.bulk_create(sess.id, segments_data)
    db.commit()

    return success(_to_session(sess, db, api_key.id))


@router.get("/sessions", response_model=ResponseEnvelope[CorrectionSessionListData])
def list_sessions(
    page: int = 1,
    limit: int = 20,
    api_key: ApiKey = Depends(require_scope("asr:read")),
    db: Session = Depends(get_db),
) -> ResponseEnvelope[CorrectionSessionListData]:
    """列出本 tenant 所有校正工作階段（分頁）。"""
    repo = CorrectionSessionRepository(db, api_key.id)
    items, total = repo.list_by_api_key(page=page, limit=limit)
    total_pages = max(1, math.ceil(total / limit)) if total > 0 else 1
    return success(
        CorrectionSessionListData(
            items=[_to_session(s, db, api_key.id) for s in items],
            pagination=PaginationMeta(
                total=total,
                page=page,
                limit=limit,
                total_pages=total_pages,
            ),
        )
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
    return success(_to_session(sess, db, api_key.id))


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


@router.post("/sessions/{session_id}/export-jsonl")
def export_jsonl(
    session_id: int,
    api_key: ApiKey = Depends(require_scope("asr:write")),
    db: Session = Depends(get_db),
) -> Response:
    sess = CorrectionSessionRepository(db, api_key.id).get(session_id)
    if sess is None:
        raise CorrectionSessionNotFoundError(details={"session_id": session_id})
    payload = session_to_jsonl(db, session_id, api_key.id)
    return Response(
        content=payload,
        media_type="application/x-ndjson",
        headers={
            "Content-Disposition": f'attachment; filename="correction_session_{session_id}.jsonl"'
        },
    )


@router.post("/sessions/{session_id}/export-excel")
def export_excel(
    session_id: int,
    api_key: ApiKey = Depends(require_scope("asr:write")),
    db: Session = Depends(get_db),
) -> Response:
    sess = CorrectionSessionRepository(db, api_key.id).get(session_id)
    if sess is None:
        raise CorrectionSessionNotFoundError(details={"session_id": session_id})
    raw = session_to_excel_bytes(db, session_id, api_key.id)
    return Response(
        content=raw,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="correction_session_{session_id}.xlsx"'
        },
    )


@router.post(
    "/sessions/{session_id}/evaluate-quality",
    response_model=ResponseEnvelope[QualityEvalData],
)
def evaluate_quality(
    session_id: int,
    api_key: ApiKey = Depends(require_scope("asr:write")),
    db: Session = Depends(get_db),
) -> ResponseEnvelope[QualityEvalData]:
    sess = CorrectionSessionRepository(db, api_key.id).get(session_id)
    if sess is None:
        raise CorrectionSessionNotFoundError(details={"session_id": session_id})
    result = evaluate_session_quality(db, session_id, api_key.id)
    return success(QualityEvalData(**result))


# ---------------------------------------------------------------------------
# Test-only seed endpoint — only enabled when ENV != "production".
# Used by Playwright E2E fixtures to create a correction session with
# pre-populated segments without needing a real audio upload.
# ---------------------------------------------------------------------------
@router.post("/sessions/_test/seed")
def test_seed_session(
    api_key: ApiKey = Depends(require_scope("asr:write")),
    db: Session = Depends(get_db),
    segment_count: int = 3,
) -> ResponseEnvelope[dict[str, int]]:
    """建立測試用 CorrectionSession 與 N 個假段落（僅非 production 環境啟用）。"""
    settings = get_settings()
    if settings.ENV == "production":
        raise HTTPException(status_code=404, detail="not found")

    # 建立一個佔位 Transcription（source=upload, status=completed）
    txn = Transcription(
        api_key_id=api_key.id,
        file_name="e2e_fixture.wav",
        source="upload",
        duration_sec=float(segment_count * 10),
        language="zh",
        model_name="test-model",
        model_version="0.0.0",
        status="completed",
        transcript_text="E2E fixture transcription",
    )
    db.add(txn)
    db.flush()

    sess = CorrectionSession(
        api_key_id=api_key.id,
        transcription_id=txn.id,
        name="E2E Fixture Session",
        status="in_progress",
    )
    db.add(sess)
    db.flush()

    seg_repo = CorrectionSegmentRepository(db, api_key.id)
    segments_data = [
        {
            "start_sec": float(i * 10),
            "end_sec": float((i + 1) * 10),
            "text": f"原始文字段落 {i + 1}",
        }
        for i in range(segment_count)
    ]
    seg_repo.bulk_create(sess.id, segments_data)
    db.commit()

    return success({"session_id": sess.id, "transcription_id": txn.id})
