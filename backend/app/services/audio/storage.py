from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.exceptions import AudioStorageFailedError
from app.models import AudioFile
from app.repositories.audio_file import AudioFileRepository


def store_upload(
    *,
    db: Session,
    api_key_id: int,
    raw_bytes: bytes,
    original_name: str,
    canonical_ext: str,
    verified_mime: str,
    storage_dir: Path,
) -> AudioFile:
    """將上傳 bytes 落地並插入 audio_files。"""
    if not raw_bytes:
        raise AudioStorageFailedError(message="空檔案無法儲存")

    now = datetime.now(UTC)
    sub_dir = storage_dir / f"{now.year:04d}" / f"{now.month:02d}"
    sub_dir.mkdir(parents=True, exist_ok=True)
    file_id = uuid4()
    target = sub_dir / f"{file_id}.{canonical_ext}"
    try:
        target.write_bytes(raw_bytes)
    except OSError as e:
        raise AudioStorageFailedError(details={"reason": str(e)}) from e

    repo = AudioFileRepository(db, api_key_id)
    return repo.create(
        original_name=original_name,
        storage_path=str(target),
        file_size=len(raw_bytes),
        mime_type=None,
        verified_mime_type=verified_mime,
    )
