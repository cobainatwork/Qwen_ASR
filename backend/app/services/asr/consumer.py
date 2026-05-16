from __future__ import annotations

import asyncio
from typing import Any

import structlog

from app.core.exceptions import AppException, AsrRequestTimeoutError
from app.deps.db import get_session_factory
from app.services.asr.queue import AsrJob, QueueBackend
from app.services.asr.transcriber import Transcriber

logger = structlog.get_logger(__name__)


class AsrConsumer:
    """背景 task：從 queue 取 job → 呼叫 Transcriber → 將結果寫入 future。"""

    def __init__(self, queue: QueueBackend, max_duration_sec: int) -> None:
        self.queue = queue
        self.max_duration_sec = max_duration_sec
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="asr-consumer")

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: S110
                pass

    async def _run(self) -> None:
        SessionLocal = get_session_factory()
        logger.info("asr consumer started")
        while not self._stop.is_set():
            try:
                job = await self.queue.dequeue()
            except asyncio.CancelledError:
                break
            await self._handle_job(SessionLocal, job)

    async def _handle_job(self, SessionLocal: Any, job: AsrJob) -> None:
        with SessionLocal() as db:
            transcriber = Transcriber(db, job.api_key_id, self.max_duration_sec)
            try:
                outcome = await transcriber.run(job)
                if job.future is not None and not job.future.done():
                    job.future.set_result(outcome.transcription_id)
            except AppException as e:
                logger.warning("job failed", job_id=job.job_id, code=e.code)
                if job.future is not None and not job.future.done():
                    job.future.set_exception(e)
            except Exception as e:
                logger.exception("job unexpected failure", job_id=job.job_id)
                if job.future is not None and not job.future.done():
                    job.future.set_exception(e)


async def wait_for_job(job: AsrJob, timeout: float) -> int:  # noqa: ASYNC109
    """等待 consumer 完成，回傳 transcription_id。"""
    if job.future is None:
        raise RuntimeError("AsrJob.future 未設定")
    try:
        return await asyncio.wait_for(job.future, timeout=timeout)
    except TimeoutError as e:
        raise AsrRequestTimeoutError(details={"job_id": job.job_id, "timeout_sec": timeout}) from e
