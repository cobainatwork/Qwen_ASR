import pytest
from app.core.exceptions import (
    AsrAudioTooLongError,
    AsrCudaError,
    AsrInferenceFailedError,
    NotFoundError,
)
from app.repositories.audio_file import AudioFileRepository
from app.services.asr.engine import AsrEngineManager
from app.services.asr.queue import AsrJob
from app.services.asr.transcriber import Transcriber
from sqlalchemy import text
from sqlalchemy.orm import Session


class _MockEngine:
    def __init__(self, output: dict | Exception) -> None:
        self.output = output

    async def generate(self, **kwargs):  # type: ignore[no-untyped-def]
        if isinstance(self.output, Exception):
            raise self.output
        return self.output

    async def abort_all(self) -> None:
        return None


@pytest.fixture(autouse=True)
def _reset_engine() -> None:
    AsrEngineManager.set_engine_for_test(None, model_version="unknown")
    yield
    AsrEngineManager.set_engine_for_test(None, model_version="unknown")


def _seed_audio(db: Session, api_key_id: int, duration_sec: float | None = 5.0) -> int:
    repo = AudioFileRepository(db, api_key_id)
    af = repo.create(
        original_name="x.wav",
        storage_path="/tmp/x.wav",
        file_size=1024,
    )
    if duration_sec is not None:
        repo.update_after_resample(af.id, original_sample_rate=16000, duration_sec=duration_sec)
    db.commit()
    return af.id


@pytest.mark.asyncio
async def test_run_success_writes_transcription(
    db_session: Session, seed_api_key: int
) -> None:
    audio_id = _seed_audio(db_session, seed_api_key)
    mock_ts = [{"text": "你好", "start": 0.0, "end": 0.5}]
    AsrEngineManager.set_engine_for_test(
        _MockEngine({"text": "你好世界", "timestamps": mock_ts}),
        model_version="MOCK@1",
    )
    transcriber = Transcriber(db_session, seed_api_key, max_duration_sec=1200)
    outcome = await transcriber.run(
        AsrJob(audio_file_id=audio_id, api_key_id=seed_api_key, options={"return_timestamps": True})
    )
    assert outcome.text == "你好世界"
    assert outcome.model_version == "MOCK@1"

    row = db_session.execute(
        text("SELECT status, transcript_text, model_version FROM transcriptions WHERE id = :i"),
        {"i": outcome.transcription_id},
    ).first()
    assert row is not None
    assert row[0] == "completed"
    assert row[1] == "你好世界"
    assert row[2] == "MOCK@1"


@pytest.mark.asyncio
async def test_run_rejects_audio_too_long(db_session: Session, seed_api_key: int) -> None:
    audio_id = _seed_audio(db_session, seed_api_key, duration_sec=2000.0)
    AsrEngineManager.set_engine_for_test(_MockEngine({"text": ""}), model_version="MOCK")
    t = Transcriber(db_session, seed_api_key, max_duration_sec=1200)
    with pytest.raises(AsrAudioTooLongError):
        await t.run(AsrJob(audio_file_id=audio_id, api_key_id=seed_api_key, options={}))


@pytest.mark.asyncio
async def test_run_missing_audio_raises_not_found(
    db_session: Session, seed_api_key: int
) -> None:
    AsrEngineManager.set_engine_for_test(_MockEngine({"text": ""}), model_version="MOCK")
    t = Transcriber(db_session, seed_api_key, max_duration_sec=1200)
    with pytest.raises(NotFoundError):
        await t.run(AsrJob(audio_file_id=999_999, api_key_id=seed_api_key, options={}))


@pytest.mark.asyncio
async def test_run_cuda_error_marks_failed_and_raises(
    db_session: Session, seed_api_key: int
) -> None:
    audio_id = _seed_audio(db_session, seed_api_key)
    AsrEngineManager.set_engine_for_test(
        _MockEngine(RuntimeError("CudaOutOfMemory")), model_version="MOCK"
    )
    t = Transcriber(db_session, seed_api_key, max_duration_sec=1200)
    with pytest.raises(AsrCudaError):
        await t.run(AsrJob(audio_file_id=audio_id, api_key_id=seed_api_key, options={}))

    row = db_session.execute(
        text("SELECT status FROM transcriptions WHERE api_key_id = :a ORDER BY id DESC"),
        {"a": seed_api_key},
    ).first()
    assert row is not None and row[0] == "failed"


@pytest.mark.asyncio
async def test_run_generic_error_marks_failed_and_raises_inference(
    db_session: Session, seed_api_key: int
) -> None:
    audio_id = _seed_audio(db_session, seed_api_key)
    AsrEngineManager.set_engine_for_test(
        _MockEngine(ValueError("bad output")), model_version="MOCK"
    )
    t = Transcriber(db_session, seed_api_key, max_duration_sec=1200)
    with pytest.raises(AsrInferenceFailedError):
        await t.run(AsrJob(audio_file_id=audio_id, api_key_id=seed_api_key, options={}))
