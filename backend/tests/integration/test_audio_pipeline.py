from pathlib import Path

import pytest
from app.repositories.audio_file import AudioFileRepository
from app.services.audio import (
    FireRedVADService,
    Segment,
    resample_to_16k_mono,
    store_upload,
    verify_mime,
)
from sqlalchemy.orm import Session

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "audio"
SUPPORTED = ["wav", "mp3", "mp4", "flac", "aac", "ogg", "m4a"]


class _FakeVadModel:
    def infer(self, wav_path: str) -> list[tuple[float, float]]:
        return [(0.0, 1.0)]


@pytest.fixture(autouse=True)
def _stub_vad() -> None:
    FireRedVADService.set_model(_FakeVadModel())
    yield
    FireRedVADService.set_model(None)


@pytest.mark.asyncio
async def test_full_pipeline_8khz_to_16khz(
    db_session: Session, seed_api_key: int, tmp_path: Path
) -> None:
    raw_bytes = (FIXTURES / "valid_8k_mono.wav").read_bytes()

    # 1. MIME 校驗
    mime, ext = verify_mime(raw_bytes, SUPPORTED)
    assert ext == "wav"

    # 2. 落地儲存
    audio = store_upload(
        db=db_session,
        api_key_id=seed_api_key,
        raw_bytes=raw_bytes,
        original_name="user_8k.wav",
        canonical_ext=ext,
        verified_mime=mime,
        storage_dir=tmp_path / "storage",
    )

    # 3. 重取樣
    result = await resample_to_16k_mono(Path(audio.storage_path), tmp_path / "processed")
    assert result.resampling_warning is True
    assert result.original_sample_rate == 8000

    # 4. 寫回 audio_files
    AudioFileRepository(db_session, seed_api_key).update_after_resample(
        audio.id,
        original_sample_rate=result.original_sample_rate,
        duration_sec=result.duration_sec,
    )

    # 5. VAD 偵測
    segments = await FireRedVADService.detect_speech(result.output_path)
    assert len(segments) >= 1
    assert isinstance(segments[0], Segment)

    # 驗證 DB 狀態
    db_session.refresh(audio)
    assert audio.original_sample_rate == 8000
    assert audio.duration_sec is not None
