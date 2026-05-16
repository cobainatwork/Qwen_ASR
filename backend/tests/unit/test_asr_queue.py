import asyncio

import pytest
from app.core.exceptions import QueueFullError
from app.services.asr.queue import AsrJob, AsyncioQueueBackend, QueuePriority


@pytest.mark.asyncio
async def test_enqueue_dequeue_basic() -> None:
    q = AsyncioQueueBackend(realtime_max=5, batch_max=5)
    job = AsrJob(audio_file_id=1, api_key_id=42)
    job_id = await q.enqueue(job, QueuePriority.BATCH)
    assert q.size() == 1
    got = await asyncio.wait_for(q.dequeue(), timeout=1.0)
    assert got.job_id == job_id


@pytest.mark.asyncio
async def test_realtime_priority_over_batch() -> None:
    q = AsyncioQueueBackend(realtime_max=5, batch_max=5)
    batch_job = AsrJob(audio_file_id=1, api_key_id=1)
    rt_job = AsrJob(audio_file_id=2, api_key_id=1)
    await q.enqueue(batch_job, QueuePriority.BATCH)
    await q.enqueue(rt_job, QueuePriority.REALTIME)
    first = await q.dequeue()
    assert first.job_id == rt_job.job_id
    second = await q.dequeue()
    assert second.job_id == batch_job.job_id


@pytest.mark.asyncio
async def test_full_queue_rejects() -> None:
    q = AsyncioQueueBackend(realtime_max=1, batch_max=1)
    await q.enqueue(AsrJob(audio_file_id=1, api_key_id=1), QueuePriority.BATCH)
    with pytest.raises(QueueFullError):
        await q.enqueue(AsrJob(audio_file_id=2, api_key_id=1), QueuePriority.BATCH)


@pytest.mark.asyncio
async def test_cancel_skips_job() -> None:
    q = AsyncioQueueBackend(realtime_max=5, batch_max=5)
    j1 = AsrJob(audio_file_id=1, api_key_id=1)
    j2 = AsrJob(audio_file_id=2, api_key_id=1)
    await q.enqueue(j1, QueuePriority.BATCH)
    await q.enqueue(j2, QueuePriority.BATCH)
    cancelled = await q.cancel(j1.job_id)
    assert cancelled is True
    first = await q.dequeue()
    assert first.job_id == j2.job_id


@pytest.mark.asyncio
async def test_status_reports_state() -> None:
    q = AsyncioQueueBackend(realtime_max=5, batch_max=5)
    job = AsrJob(audio_file_id=1, api_key_id=1)
    await q.enqueue(job, QueuePriority.BATCH)
    s = await q.status(job.job_id)
    assert s["state"] == "queued"
    assert s["priority"] == "batch"


@pytest.mark.asyncio
async def test_status_unknown_job() -> None:
    q = AsyncioQueueBackend(realtime_max=5, batch_max=5)
    s = await q.status("does-not-exist")
    assert s["state"] == "unknown"


def test_size_by_priority() -> None:
    q = AsyncioQueueBackend(realtime_max=5, batch_max=5)
    asyncio.run(q.enqueue(AsrJob(audio_file_id=1, api_key_id=1), QueuePriority.BATCH))
    asyncio.run(q.enqueue(AsrJob(audio_file_id=2, api_key_id=1), QueuePriority.REALTIME))
    assert q.size(QueuePriority.BATCH) == 1
    assert q.size(QueuePriority.REALTIME) == 1
    assert q.size() == 2
