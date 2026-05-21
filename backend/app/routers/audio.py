"""Audio file streaming endpoint with HTTP Range support.

wavesurfer.js 7 sends Range requests when loading large audio files.
This endpoint parses the Range header and returns 206 Partial Content.
"""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.deps.auth import require_scope
from app.deps.db import get_db
from app.models import ApiKey
from app.repositories.audio_file import AudioFileRepository

router = APIRouter(prefix="/api/v1/audio", tags=["audio"])

_CHUNK_SIZE = 64 * 1024  # 64 KB


def _parse_range(range_header: str, file_size: int) -> tuple[int, int]:
    """Parse `Range: bytes=START-END`. Returns (start, end) inclusive.

    Raises HTTPException 416 if the range is invalid or out-of-bounds.
    """
    if not range_header.startswith("bytes="):
        raise HTTPException(
            status_code=416,
            detail="invalid range unit",
            headers={"Content-Range": f"bytes */{file_size}"},
        )
    raw = range_header[6:]
    try:
        start_str, end_str = raw.split("-", 1)
        start = int(start_str) if start_str else 0
        end = int(end_str) if end_str else file_size - 1
    except ValueError as exc:
        raise HTTPException(
            status_code=416,
            detail="invalid range header",
            headers={"Content-Range": f"bytes */{file_size}"},
        ) from exc
    if start < 0 or start >= file_size or end >= file_size or start > end:
        raise HTTPException(
            status_code=416,
            detail="range not satisfiable",
            headers={"Content-Range": f"bytes */{file_size}"},
        )
    return start, end


@router.get("/{audio_file_id}/stream")
def stream_audio(
    audio_file_id: int,
    request: Request,
    api_key: ApiKey = Depends(require_scope("asr:read")),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Stream an audio file with optional HTTP Range support."""
    audio = AudioFileRepository(db, api_key.id).get(audio_file_id)
    if audio is None:
        raise HTTPException(status_code=404, detail="audio file not found")

    file_path = Path(audio.storage_path)
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="audio file missing on disk")

    file_size = file_path.stat().st_size
    media_type = audio.mime_type or "application/octet-stream"
    range_header = request.headers.get("range")

    if range_header is None:
        def _iter_full() -> Iterator[bytes]:
            with file_path.open("rb") as f:
                while chunk := f.read(_CHUNK_SIZE):
                    yield chunk

        return StreamingResponse(
            _iter_full(),
            media_type=media_type,
            headers={
                "Accept-Ranges": "bytes",
                "Content-Length": str(file_size),
                "Cache-Control": "private, max-age=3600",
            },
        )

    start, end = _parse_range(range_header, file_size)
    length = end - start + 1

    def _iter_range() -> Iterator[bytes]:
        with file_path.open("rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                read_size = min(_CHUNK_SIZE, remaining)
                chunk = f.read(read_size)
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    return StreamingResponse(
        _iter_range(),
        status_code=206,
        media_type=media_type,
        headers={
            "Accept-Ranges": "bytes",
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Content-Length": str(length),
            "Cache-Control": "private, max-age=3600",
        },
    )
