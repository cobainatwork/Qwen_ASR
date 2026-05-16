from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from app.core.exceptions import QueueFullError


class QueuePriority(StrEnum):
    REALTIME = "realtime"
    BATCH = "batch"


@dataclass
class AsrJob:
    job_id: str = field(default_factory=lambda: str(uuid4()))
    audio_file_id: int = 0
    api_key_id: int = 0
    options: dict[str, Any] = field(default_factory=dict)
    enqueued_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    future: asyncio.Future[int] | None = None  # transcription_id


class QueueBackend(ABC):
    @abstractmethod
    async def enqueue(self, job: AsrJob, priority: QueuePriority) -> str: ...

    @abstractmethod
    async def dequeue(self) -> AsrJob: ...

    @abstractmethod
    async def cancel(self, job_id: str) -> bool: ...

    @abstractmethod
    async def status(self, job_id: str) -> dict[str, Any]: ...

    @abstractmethod
    def size(self, priority: QueuePriority | None = None) -> int: ...


class AsyncioQueueBackend(QueueBackend):
    """V1 預設實作：基於 asyncio.Queue 的雙通道排程。"""

    def __init__(self, realtime_max: int, batch_max: int) -> None:
        self._realtime: asyncio.Queue[AsrJob] = asyncio.Queue(maxsize=realtime_max)
        self._batch: asyncio.Queue[AsrJob] = asyncio.Queue(maxsize=batch_max)
        self._jobs: dict[str, tuple[AsrJob, QueuePriority]] = {}
        self._cancelled: set[str] = set()
        self._lock = asyncio.Lock()

    async def enqueue(self, job: AsrJob, priority: QueuePriority) -> str:
        queue = self._realtime if priority == QueuePriority.REALTIME else self._batch
        if queue.full():
            raise QueueFullError(details={"priority": priority.value, "size": queue.qsize()})
        async with self._lock:
            self._jobs[job.job_id] = (job, priority)
        await queue.put(job)
        return job.job_id

    async def dequeue(self) -> AsrJob:
        """優先 realtime，realtime 空才從 batch 取。"""
        while True:
            if not self._realtime.empty():
                job = await self._realtime.get()
            else:
                # 短暫等待 realtime（10 ms）若仍空則 fallback batch
                try:
                    job = await asyncio.wait_for(self._realtime.get(), timeout=0.01)
                except TimeoutError:
                    job = await self._batch.get()
            if job.job_id in self._cancelled:
                self._cancelled.discard(job.job_id)
                continue
            return job

    async def cancel(self, job_id: str) -> bool:
        async with self._lock:
            if job_id not in self._jobs:
                return False
            self._cancelled.add(job_id)
            return True

    async def status(self, job_id: str) -> dict[str, Any]:
        async with self._lock:
            entry = self._jobs.get(job_id)
        if entry is None:
            return {"job_id": job_id, "state": "unknown"}
        _, priority = entry
        state = "cancelled" if job_id in self._cancelled else "queued"
        return {"job_id": job_id, "state": state, "priority": priority.value}

    def size(self, priority: QueuePriority | None = None) -> int:
        if priority == QueuePriority.REALTIME:
            return self._realtime.qsize()
        if priority == QueuePriority.BATCH:
            return self._batch.qsize()
        return self._realtime.qsize() + self._batch.qsize()
