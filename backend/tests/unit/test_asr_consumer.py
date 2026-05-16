import asyncio

import pytest
from app.core.exceptions import AsrRequestTimeoutError
from app.repositories.audio_file import AudioFileRepository
from app.services.asr.consumer import AsrConsumer, wait_for_job
from app.services.asr.engine import AsrEngineManager
from app.services.asr.queue import AsrJob, AsyncioQueueBackend, QueuePriority
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


@pytest.mark.asyncio
async def test_consumer_processes_job(
    db_session: Session, seed_api_key: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 注入測試用 session factory：patch consumer 模組內已 import 的 get_session_factory
    # consumer._run() 呼叫鏈：SessionLocal = get_session_factory()；with SessionLocal() as db
    # get_session_factory 需回傳 callable，該 callable 回傳 context manager（包裝 db_session）
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

    AsrEngineManager.set_engine_for_test(
        _MockEngine({"text": "hello", "timestamps": None}), model_version="MOCK"
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
    transcription_id = await wait_for_job(job, timeout=10.0)
    assert transcription_id > 0

    await consumer.stop()


@pytest.mark.asyncio
async def test_wait_for_job_timeout_raises() -> None:
    job = AsrJob(future=asyncio.get_event_loop().create_future())
    with pytest.raises(AsrRequestTimeoutError):
        await wait_for_job(job, timeout=0.1)
