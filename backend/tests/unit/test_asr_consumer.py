import asyncio
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from app.core.exceptions import AsrRequestTimeoutError
from app.repositories.audio_file import AudioFileRepository
from app.services.asr.consumer import AsrConsumer, wait_for_job
from app.services.asr.engine import AsrEngineManager
from app.services.asr.queue import AsrJob, AsyncioQueueBackend, QueuePriority
from sqlalchemy.orm import Session


class _MockAsrModel:
    """仿 Qwen3ASRModel.LLM 的 mock：transcribe 為同步方法（qwen-asr 0.0.6 介面）。"""

    def __init__(self, output: Any | Exception) -> None:
        self.output = output

    def transcribe(self, audio: Any, **kwargs: Any) -> list[Any]:  # noqa: ARG002
        if isinstance(self.output, Exception):
            raise self.output
        return [self.output]


def _make_mock_result(text: str = "hello", language: str = "en") -> Any:
    """建立仿 qwen-asr TranscriptionResult 的 mock 物件。"""
    result = MagicMock()
    result.text = text
    result.language = language
    result.time_stamps = None
    return result


@pytest.fixture(autouse=True)
def _reset_engine(monkeypatch: pytest.MonkeyPatch) -> Any:
    """每個測試前重置 engine，並注入最小 Settings 使後處理階段全數關閉。"""
    import app.core.config as _config_mod
    from app.core.config import Settings

    # 必須在 monkeypatch 之前保留原始 get_settings 參考，
    # 因為 monkeypatch.setattr 會將 _config_mod.get_settings 替換為 lambda，
    # 之後直接呼叫 .cache_clear() 會 AttributeError（lambda 沒有 cache_clear）。
    _original_get_settings = _config_mod.get_settings
    _original_get_settings.cache_clear()

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


@pytest.mark.asyncio
async def test_consumer_processes_job(
    db_session: Session, seed_api_key: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 注入測試用 session factory：patch consumer 模組內已 import 的 get_session_factory
    # consumer._run() 呼叫鏈：SessionLocal = get_session_factory()；with SessionLocal() as db
    from contextlib import contextmanager

    import app.services.asr.consumer as consumer_module

    @contextmanager  # type: ignore[arg-type]
    def _session_cm():  # type: ignore[return]
        yield db_session

    def _fake_session_callable() -> object:
        return _session_cm()

    monkeypatch.setattr(consumer_module, "get_session_factory", lambda: _fake_session_callable)

    # 建 audio file
    afr = AudioFileRepository(db_session, seed_api_key)
    af = afr.create(original_name="t.wav", storage_path="/tmp/t.wav", file_size=1)
    afr.update_after_resample(af.id, original_sample_rate=16000, duration_sec=2.0)
    db_session.commit()

    # 注入 mock ASR：transcribe 回傳 mock TranscriptionResult
    AsrEngineManager.set_asr_for_test(
        _MockAsrModel(_make_mock_result(text="hello", language="en")),
        model_version="MOCK",
    )

    q = AsyncioQueueBackend(realtime_max=5, batch_max=5)
    consumer = AsrConsumer(q, max_duration_sec=1200)
    await consumer.start()

    job = AsrJob(
        audio_file_id=af.id,
        api_key_id=seed_api_key,
        options={"return_timestamps": False},
        future=asyncio.get_event_loop().create_future(),
    )
    await q.enqueue(job, QueuePriority.BATCH)

    # Patch _load_wav_as_numpy：mock audio file 不需實際存在
    with patch(
        "app.services.asr.transcriber._load_wav_as_numpy",
        return_value=(MagicMock(), 16000),
    ):
        transcription_id = await wait_for_job(job, timeout=10.0)

    assert transcription_id > 0

    await consumer.stop()


@pytest.mark.asyncio
async def test_wait_for_job_timeout_raises() -> None:
    job = AsrJob(future=asyncio.get_event_loop().create_future())
    with pytest.raises(AsrRequestTimeoutError):
        await wait_for_job(job, timeout=0.1)
