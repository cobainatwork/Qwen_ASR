"""Dataset 樣本處理：MIME 校驗 → UUID 儲存 → 16 kHz 重取樣 → 寫入 audio_files。"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import DatasetSampleInvalidError
from app.models import AudioFile
from app.repositories.audio_file import AudioFileRepository
from app.services.audio.mime import verify_mime
from app.services.audio.resampler import resample_to_16k_mono
from app.services.audio.storage import store_upload


async def process_sample(
    *,
    db: Session,
    api_key_id: int,
    raw_bytes: bytes,
    original_name: str,
    transcript: str,
    settings: Settings,
) -> tuple[AudioFile, float]:
    """處理單一樣本，回傳 (audio_file, duration_sec)。

    Raises:
        AudioMimeInvalidError / AudioStorageFailedError / AudioResampleFailedError
        DatasetSampleInvalidError: transcript 為空或過長
    """
    if not transcript.strip():
        raise DatasetSampleInvalidError(message="樣本 transcript 不可為空")
    if len(transcript) > 5000:
        raise DatasetSampleInvalidError(
            message=f"樣本 transcript 超過 5000 字（實際 {len(transcript)}）"
        )

    mime, ext = verify_mime(raw_bytes, settings.supported_formats_list)
    audio = store_upload(
        db=db,
        api_key_id=api_key_id,
        raw_bytes=raw_bytes,
        original_name=original_name,
        canonical_ext=ext,
        verified_mime=mime,
        storage_dir=settings.AUDIO_STORAGE_DIR,
    )
    db.commit()

    resample = await resample_to_16k_mono(
        Path(audio.storage_path),
        settings.AUDIO_STORAGE_DIR / "dataset_processed",
    )
    AudioFileRepository(db, api_key_id).update_after_resample(
        audio.id,
        original_sample_rate=resample.original_sample_rate,
        duration_sec=resample.duration_sec,
    )
    db.commit()
    return audio, resample.duration_sec
