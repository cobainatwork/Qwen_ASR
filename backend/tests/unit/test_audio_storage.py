from pathlib import Path

import pytest
from app.core.exceptions import AudioStorageFailedError
from app.services.audio.storage import store_upload
from sqlalchemy.orm import Session


def test_store_upload_writes_file_and_inserts_db(
    db_session: Session, seed_api_key: int, tmp_path: Path
) -> None:
    af = store_upload(
        db=db_session,
        api_key_id=seed_api_key,
        raw_bytes=b"binary-data",
        original_name="hello.wav",
        canonical_ext="wav",
        verified_mime="audio/wav",
        storage_dir=tmp_path,
    )
    assert af.api_key_id == seed_api_key
    assert af.original_name == "hello.wav"
    assert af.verified_mime_type == "audio/wav"
    assert Path(af.storage_path).exists()
    assert Path(af.storage_path).read_bytes() == b"binary-data"


def test_store_upload_uses_uuid_not_original_name(
    db_session: Session, seed_api_key: int, tmp_path: Path
) -> None:
    af = store_upload(
        db=db_session,
        api_key_id=seed_api_key,
        raw_bytes=b"x",
        original_name="../etc/passwd",
        canonical_ext="wav",
        verified_mime="audio/wav",
        storage_dir=tmp_path,
    )
    # 路徑必須在 storage_dir 下，且檔名為 UUID
    assert tmp_path in Path(af.storage_path).parents
    assert ".." not in af.storage_path


def test_store_upload_rejects_empty_bytes(
    db_session: Session, seed_api_key: int, tmp_path: Path
) -> None:
    with pytest.raises(AudioStorageFailedError, match="空檔案"):
        store_upload(
            db=db_session,
            api_key_id=seed_api_key,
            raw_bytes=b"",
            original_name="empty.wav",
            canonical_ext="wav",
            verified_mime="audio/wav",
            storage_dir=tmp_path,
        )


def test_store_upload_writes_to_yyyy_mm_subdir(
    db_session: Session, seed_api_key: int, tmp_path: Path
) -> None:
    af = store_upload(
        db=db_session,
        api_key_id=seed_api_key,
        raw_bytes=b"x",
        original_name="a.wav",
        canonical_ext="wav",
        verified_mime="audio/wav",
        storage_dir=tmp_path,
    )
    parts = Path(af.storage_path).parts
    # 父目錄結構：tmp_path / YYYY / MM / UUID.wav
    assert len(parts) >= 4
    assert parts[-3].isdigit() and len(parts[-3]) == 4
    assert parts[-2].isdigit() and len(parts[-2]) == 2
