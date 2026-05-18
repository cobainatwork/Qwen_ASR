from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

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
from app.services.asr.transcriber import Transcriber, _parse_timestamps
from sqlalchemy import text
from sqlalchemy.orm import Session


def _make_mock_result(
    text: str = "你好世界",
    language: str = "zh",
    time_stamps: list[Any] | None = None,
) -> Any:
    """建立仿 qwen-asr TranscriptionResult 的 mock 物件。"""
    result = MagicMock()
    result.text = text
    result.language = language
    result.time_stamps = time_stamps
    return result


def _make_ts(text: str, start: float, end: float) -> Any:
    ts = MagicMock()
    ts.text = text
    ts.start_time = start
    ts.end_time = end
    return ts


class _MockAsrModel:
    """仿 Qwen3ASRModel.LLM 的 mock：transcribe 為同步方法。"""

    def __init__(self, result: Any | Exception) -> None:
        self._result = result

    def transcribe(self, audio: Any, **kwargs: Any) -> list[Any]:
        if isinstance(self._result, Exception):
            raise self._result
        return [self._result]


@pytest.fixture(autouse=True)
def _reset_engine(monkeypatch: pytest.MonkeyPatch) -> Any:
    """每個測試前重置 engine，並注入最小 Settings 使後處理全數關閉。"""
    import app.core.config as _config_mod

    # 必須在 monkeypatch 之前保留原始 get_settings 參考，
    # 因為 monkeypatch.setattr 會將 _config_mod.get_settings 替換為 lambda，
    # 之後直接呼叫 .cache_clear() 會 AttributeError（lambda 沒有 cache_clear）。
    _original_get_settings = _config_mod.get_settings
    _original_get_settings.cache_clear()

    from app.core.config import Settings

    fake_settings = Settings(
        API_KEY="unit-test",
        DATABASE_URL="postgresql+psycopg://u:p@h/d",
        DB_PASSWORD="p",
        THIRD_PARTY_LICENSE_ACK=True,
        ALIGNER_ENABLED=False,
        DIARIZATION_ENABLED=False,
        POST_PROCESSING_ENABLED=False,
        CORRECTION_NEC_ENABLED=False,
        CORRECTION_KENLM_ENABLED=False,
        CORRECTION_HOMOPHONE_ENABLED=False,
        CORRECTION_LLM_BACKEND="none",
    )  # type: ignore[call-arg]
    monkeypatch.setattr("app.core.config.get_settings", lambda: fake_settings)

    AsrEngineManager.set_asr_for_test(None, model_version="unknown")
    yield
    AsrEngineManager.set_asr_for_test(None, model_version="unknown")
    _original_get_settings.cache_clear()


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


# ── _parse_timestamps 單元測試 ────────────────────────────────────────────────


def test_parse_timestamps_returns_none_when_none() -> None:
    assert _parse_timestamps(None) is None


def test_parse_timestamps_converts_ts_objects() -> None:
    ts1 = _make_ts("你好", 0.0, 0.5)
    ts2 = _make_ts("世界", 0.5, 1.2)
    result = _parse_timestamps([ts1, ts2])
    assert result == [
        {"text": "你好", "start": 0.0, "end": 0.5},
        {"text": "世界", "start": 0.5, "end": 1.2},
    ]


# ── Transcriber.run 整合測試（mock DB + mock ASR）────────────────────────────


@pytest.mark.asyncio
async def test_run_success_writes_transcription(
    db_session: Session, seed_api_key: int
) -> None:
    audio_id = _seed_audio(db_session, seed_api_key)
    ts = [_make_ts("你好", 0.0, 0.5)]
    mock_result = _make_mock_result(text="你好世界", language="zh", time_stamps=ts)
    mock_asr = _MockAsrModel(mock_result)

    AsrEngineManager.set_asr_for_test(mock_asr, model_version="MOCK@1")

    transcriber = Transcriber(db_session, seed_api_key, max_duration_sec=1200)
    with patch(
        "app.services.asr.transcriber._load_wav_as_numpy",
        return_value=(MagicMock(), 16000),
    ):
        outcome = await transcriber.run(
            AsrJob(
                audio_file_id=audio_id,
                api_key_id=seed_api_key,
                options={"return_timestamps": True},
            )
        )

    assert outcome.text == "你好世界"
    assert outcome.model_version == "MOCK@1"
    assert outcome.timestamps == [{"text": "你好", "start": 0.0, "end": 0.5}]
    assert outcome.language == "zh"

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
    AsrEngineManager.set_asr_for_test(_MockAsrModel(MagicMock()), model_version="MOCK")
    t = Transcriber(db_session, seed_api_key, max_duration_sec=1200)
    with pytest.raises(AsrAudioTooLongError):
        await t.run(AsrJob(audio_file_id=audio_id, api_key_id=seed_api_key, options={}))


@pytest.mark.asyncio
async def test_run_missing_audio_raises_not_found(
    db_session: Session, seed_api_key: int
) -> None:
    AsrEngineManager.set_asr_for_test(_MockAsrModel(MagicMock()), model_version="MOCK")
    t = Transcriber(db_session, seed_api_key, max_duration_sec=1200)
    with pytest.raises(NotFoundError):
        await t.run(AsrJob(audio_file_id=999_999, api_key_id=seed_api_key, options={}))


@pytest.mark.asyncio
async def test_run_cuda_error_marks_failed_and_raises(
    db_session: Session, seed_api_key: int
) -> None:
    audio_id = _seed_audio(db_session, seed_api_key)
    AsrEngineManager.set_asr_for_test(
        _MockAsrModel(RuntimeError("CudaOutOfMemory")), model_version="MOCK"
    )
    t = Transcriber(db_session, seed_api_key, max_duration_sec=1200)
    with patch(
        "app.services.asr.transcriber._load_wav_as_numpy",
        return_value=(MagicMock(), 16000),
    ):
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
    AsrEngineManager.set_asr_for_test(
        _MockAsrModel(ValueError("bad output")), model_version="MOCK"
    )
    t = Transcriber(db_session, seed_api_key, max_duration_sec=1200)
    with patch(
        "app.services.asr.transcriber._load_wav_as_numpy",
        return_value=(MagicMock(), 16000),
    ):
        with pytest.raises(AsrInferenceFailedError):
            await t.run(AsrJob(audio_file_id=audio_id, api_key_id=seed_api_key, options={}))


@pytest.mark.asyncio
async def test_run_without_timestamps_returns_none_timestamps(
    db_session: Session, seed_api_key: int
) -> None:
    """return_timestamps=False 時，outcome.timestamps 必須為 None。"""
    audio_id = _seed_audio(db_session, seed_api_key)
    mock_result = _make_mock_result(text="測試", language="zh", time_stamps=None)
    AsrEngineManager.set_asr_for_test(_MockAsrModel(mock_result), model_version="MOCK")
    t = Transcriber(db_session, seed_api_key, max_duration_sec=1200)
    with patch(
        "app.services.asr.transcriber._load_wav_as_numpy",
        return_value=(MagicMock(), 16000),
    ):
        outcome = await t.run(
            AsrJob(
                audio_file_id=audio_id,
                api_key_id=seed_api_key,
                options={"return_timestamps": False},
            )
        )
    assert outcome.timestamps is None
