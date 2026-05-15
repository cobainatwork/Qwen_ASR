# Phase 1 / M4 — ASR 推理引擎與 transcribe 端點 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 M3 預處理管線之上整合 vLLM AsyncLLMEngine 與 transcribe HTTP 端點。`POST /api/v1/asr/transcribe` 接收音檔 + 選項，依序執行預處理、入 batch 佇列、由背景 consumer 呼叫 vLLM 推理，將結果寫入 `transcriptions` 表並回傳 `ResponseEnvelope`。CI 環境以 mock vLLM 驗證；Linux GPU 環境透過 `scripts/smoke_asr.sh` 真實推理。

**Architecture:** `AsrEngineManager` 為單例，於 FastAPI lifespan 啟動載入 vLLM AsyncLLMEngine。`QueueBackend` 抽象基底 + `AsyncioQueueBackend` 雙通道（realtime / batch）；Phase 1 僅 batch 通道有實際使用。`AsrConsumer` 背景 task 在 lifespan 啟動，從佇列取 job 呼叫 `Transcriber.run()`。Transcriber 編排：取得 audio_file → 建立 transcription（status=processing）→ 呼叫 engine.generate → 解析結果 → 更新 status。HTTP 路由透過 future 機制等待 consumer 完成。

**Tech Stack:** vLLM（GPU 環境）、asyncio、Pydantic、httpx（測試）、SQLAlchemy 既有 ORM。

**對應設計文件：** `docs/superpowers/specs/2026-05-16-phase1-implementation-design.md` 第 2.5、6 章節。

---

## File Structure

| 路徑 | 動作 | 責任 |
|------|------|------|
| `backend/app/services/asr/__init__.py` | Create | 顯式 re-export |
| `backend/app/services/asr/queue.py` | Create | `QueueBackend` 抽象 + `AsyncioQueueBackend` + `AsrJob` |
| `backend/app/services/asr/engine.py` | Create | `AsrEngineManager` + `compute_model_version()` |
| `backend/app/services/asr/transcriber.py` | Create | `Transcriber.run(job)` 編排 |
| `backend/app/services/asr/consumer.py` | Create | `AsrConsumer` 背景 task 與 future 等待 |
| `backend/app/repositories/transcription.py` | Create | `TranscriptionRepository`（繼承 TenantScopedRepository） |
| `backend/app/schemas/asr.py` | Create | `TranscribeOptions` / `TranscribeData` |
| `backend/app/routers/asr.py` | Create | `POST /api/v1/asr/transcribe` |
| `backend/scripts/smoke_asr.sh` | Create | Linux GPU 環境 manual smoke 腳本 |
| `backend/tests/unit/test_asr_queue.py` | Create | 佇列單元測試 |
| `backend/tests/unit/test_asr_engine.py` | Create | engine manager / model_version 單元測試 |
| `backend/tests/unit/test_asr_transcriber.py` | Create | Transcriber 編排測試 |
| `backend/tests/integration/test_asr_transcribe.py` | Create | transcribe 端點端到端（mock vLLM） |
| `backend/app/main.py` | Modify | lifespan 加入 engine load / consumer 啟動 |

---

## Task 4.1：QueueBackend 抽象 + AsyncioQueueBackend

**Files:**
- Create: `backend/app/services/asr/__init__.py`（先寫最小版本，於 Task 4.7 補完）
- Create: `backend/app/services/asr/queue.py`
- Create: `backend/tests/unit/test_asr_queue.py`

- [ ] **Step 1：建立目錄與 minimum __init__**

```bash
cd backend
mkdir app/services/asr
```

`app/services/asr/__init__.py`：

```python
from app.services.asr.queue import AsrJob, AsyncioQueueBackend, QueueBackend, QueuePriority

__all__ = ["AsrJob", "AsyncioQueueBackend", "QueueBackend", "QueuePriority"]
```

> 註：後續 Task 4.2 / 4.3 / 4.5 完成時擴充此 __init__。

- [ ] **Step 2：撰寫 `app/services/asr/queue.py`**

```python
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
```

- [ ] **Step 3：撰寫 `tests/unit/test_asr_queue.py`**

```python
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
```

- [ ] **Step 4：執行測試**

```bash
pytest tests/unit/test_asr_queue.py -v
```

預期：7 個測試 PASS。

- [ ] **Step 5：Commit**

```bash
git add backend/app/services/asr/__init__.py backend/app/services/asr/queue.py backend/tests/unit/test_asr_queue.py
git commit -m "feat(asr): 加入 QueueBackend 抽象與 AsyncioQueueBackend（雙通道）"
```

---

## Task 4.2：AsrEngineManager 與 compute_model_version

**Files:**
- Create: `backend/app/services/asr/engine.py`
- Create: `backend/tests/unit/test_asr_engine.py`

- [ ] **Step 1：撰寫 `app/services/asr/engine.py`**

```python
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Protocol

import structlog

from app.core.config import Settings
from app.core.exceptions import AsrEngineUnavailableError

logger = structlog.get_logger(__name__)


class _AsyncEngine(Protocol):
    async def generate(self, *args: Any, **kwargs: Any) -> Any: ...

    async def abort_all(self) -> None: ...


def compute_model_version(model_dir: Path) -> str:
    """產生模型版本字串。優先序：
    1. {model_dir}/version.json 內的 `version` 欄位
    2. {model_dir}/model.safetensors 的 SHA256 前 8 字元
    3. fallback "{model_dir.name}@unknown"
    """
    version_file = model_dir / "version.json"
    if version_file.is_file():
        try:
            data = json.loads(version_file.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "version" in data:
                return f"{model_dir.name}@{data['version']}"
        except (json.JSONDecodeError, OSError):
            pass

    weights = model_dir / "model.safetensors"
    if weights.is_file():
        h = hashlib.sha256()
        with weights.open("rb") as f:
            while chunk := f.read(1024 * 1024):
                h.update(chunk)
        return f"{model_dir.name}@{h.hexdigest()[:8]}"

    return f"{model_dir.name}@unknown"


class AsrEngineManager:
    """vLLM AsyncLLMEngine 單例管理。"""

    _engine: _AsyncEngine | None = None
    _model_version: str = "unknown"

    @classmethod
    async def initialize(cls, settings: Settings) -> None:
        try:
            from vllm import AsyncEngineArgs, AsyncLLMEngine  # type: ignore[import-not-found]
        except ImportError as e:
            raise RuntimeError(
                "vllm 套件未安裝。GPU 環境請以 INSTALL_GPU_DEPS=true 重建映像。"
            ) from e

        engine_args = AsyncEngineArgs(
            model=settings.ASR_MODEL,
            download_dir=str(settings.MODEL_CACHE_DIR),
            dtype="float16",
            gpu_memory_utilization=settings.VLLM_GPU_MEMORY_UTILIZATION,
            max_num_seqs=settings.MAX_INFERENCE_BATCH,
            max_model_len=settings.ASR_MAX_TOKENS,
        )
        cls._engine = AsyncLLMEngine.from_engine_args(engine_args)
        model_dir = settings.MODEL_CACHE_DIR / settings.ASR_MODEL.replace("/", "_")
        cls._model_version = compute_model_version(model_dir)
        logger.info("ASR engine initialized", model_version=cls._model_version)

    @classmethod
    def set_engine_for_test(cls, engine: _AsyncEngine | None, model_version: str = "MOCK@TEST") -> None:
        cls._engine = engine
        cls._model_version = model_version

    @classmethod
    async def shutdown(cls) -> None:
        if cls._engine is not None:
            try:
                await cls._engine.abort_all()
            except Exception as e:
                logger.warning("engine abort_all failed", error=str(e))
            cls._engine = None

    @classmethod
    def get_engine(cls) -> _AsyncEngine:
        if cls._engine is None:
            raise AsrEngineUnavailableError()
        return cls._engine

    @classmethod
    def model_version(cls) -> str:
        return cls._model_version
```

- [ ] **Step 2：撰寫 `tests/unit/test_asr_engine.py`**

```python
import json
from pathlib import Path

import pytest

from app.core.exceptions import AsrEngineUnavailableError
from app.services.asr.engine import AsrEngineManager, compute_model_version


def test_compute_model_version_from_version_json(tmp_path: Path) -> None:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    (model_dir / "version.json").write_text(json.dumps({"version": "2026-04-01"}))
    assert compute_model_version(model_dir) == "model@2026-04-01"


def test_compute_model_version_from_safetensors(tmp_path: Path) -> None:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    (model_dir / "model.safetensors").write_bytes(b"fake-weights")
    v = compute_model_version(model_dir)
    assert v.startswith("model@")
    assert len(v.split("@")[1]) == 8


def test_compute_model_version_fallback(tmp_path: Path) -> None:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    assert compute_model_version(model_dir) == "model@unknown"


def test_compute_model_version_invalid_json_fallbacks(tmp_path: Path) -> None:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    (model_dir / "version.json").write_text("{ not-valid-json")
    assert compute_model_version(model_dir) == "model@unknown"


@pytest.fixture(autouse=True)
def _reset_engine() -> None:
    AsrEngineManager.set_engine_for_test(None, model_version="unknown")
    yield
    AsrEngineManager.set_engine_for_test(None, model_version="unknown")


def test_get_engine_raises_when_not_initialized() -> None:
    with pytest.raises(AsrEngineUnavailableError):
        AsrEngineManager.get_engine()


class _MockEngine:
    async def generate(self, **kwargs):  # type: ignore[no-untyped-def]
        return {"text": "fake"}

    async def abort_all(self) -> None:
        return None


@pytest.mark.asyncio
async def test_set_engine_for_test_and_shutdown() -> None:
    AsrEngineManager.set_engine_for_test(_MockEngine(), model_version="MOCK@1")
    assert AsrEngineManager.model_version() == "MOCK@1"
    assert AsrEngineManager.get_engine() is not None
    await AsrEngineManager.shutdown()
    with pytest.raises(AsrEngineUnavailableError):
        AsrEngineManager.get_engine()
```

- [ ] **Step 3：執行測試**

```bash
pytest tests/unit/test_asr_engine.py -v
```

預期：6 個測試 PASS。

- [ ] **Step 4：Commit**

```bash
git add backend/app/services/asr/engine.py backend/tests/unit/test_asr_engine.py
git commit -m "feat(asr): 加入 AsrEngineManager 與 compute_model_version"
```

---

## Task 4.3：Transcription Repository + Transcriber 編排

**Files:**
- Create: `backend/app/repositories/transcription.py`
- Create: `backend/app/services/asr/transcriber.py`
- Create: `backend/tests/unit/test_asr_transcriber.py`

- [ ] **Step 1：撰寫 `app/repositories/transcription.py`**

```python
from typing import Any

from app.models import Transcription
from app.repositories.base import TenantScopedRepository


class TranscriptionRepository(TenantScopedRepository[Transcription]):
    model = Transcription

    def mark_completed(
        self,
        transcription_id: int,
        *,
        transcript_text: str,
        timestamps: list[dict[str, Any]] | None,
        processing_duration_sec: float,
    ) -> None:
        rec = self.get(transcription_id)
        if rec is None:
            return
        rec.transcript_text = transcript_text
        rec.timestamps = timestamps
        rec.processing_duration_sec = processing_duration_sec
        rec.status = "completed"
        self.db.flush()

    def mark_failed(self, transcription_id: int, *, error_message: str) -> None:
        rec = self.get(transcription_id)
        if rec is None:
            return
        rec.status = "failed"
        rec.error_message = error_message
        self.db.flush()
```

- [ ] **Step 2：撰寫 `app/services/asr/transcriber.py`**

```python
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import structlog
from sqlalchemy.orm import Session

from app.core.exceptions import (
    AsrAudioTooLongError,
    AsrCudaError,
    AsrInferenceFailedError,
    NotFoundError,
)
from app.repositories.audio_file import AudioFileRepository
from app.repositories.transcription import TranscriptionRepository
from app.services.asr.engine import AsrEngineManager
from app.services.asr.queue import AsrJob

logger = structlog.get_logger(__name__)


@dataclass
class TranscribeOutcome:
    transcription_id: int
    text: str
    timestamps: list[dict[str, Any]] | None
    duration_sec: float
    processing_duration_sec: float
    model_version: str
    language: str | None


def _build_asr_prompt(audio_path: str, options: dict[str, Any]) -> dict[str, Any]:
    """組裝 vLLM 推理 prompt（依 Qwen3-ASR 介面）。"""
    return {
        "audio_path": audio_path,
        "language": options.get("language"),
        "return_timestamps": options.get("return_timestamps", True),
    }


def _parse_vllm_output(raw: Any) -> tuple[str, list[dict[str, Any]] | None]:
    """解析 vLLM generate 回應。容錯 dict 與 vLLM RequestOutput 兩種型態。"""
    if isinstance(raw, dict):
        return str(raw.get("text", "")), raw.get("timestamps")
    if hasattr(raw, "outputs") and raw.outputs:
        first = raw.outputs[0]
        return getattr(first, "text", ""), getattr(first, "timestamps", None)
    return str(raw), None


class Transcriber:
    def __init__(
        self,
        db: Session,
        api_key_id: int,
        max_duration_sec: int,
    ) -> None:
        self.db = db
        self.api_key_id = api_key_id
        self.max_duration_sec = max_duration_sec
        self.audio_repo = AudioFileRepository(db, api_key_id)
        self.tx_repo = TranscriptionRepository(db, api_key_id)

    async def run(self, job: AsrJob) -> TranscribeOutcome:
        audio = self.audio_repo.get(job.audio_file_id)
        if audio is None:
            raise NotFoundError(message="audio_file 不存在")

        if audio.duration_sec is None:
            raise AsrInferenceFailedError(message="audio_files.duration_sec 未填寫")

        if audio.duration_sec > self.max_duration_sec:
            raise AsrAudioTooLongError(
                details={
                    "limit_sec": self.max_duration_sec,
                    "actual_sec": audio.duration_sec,
                }
            )

        model_version = AsrEngineManager.model_version()
        record = self.tx_repo.create(
            file_name=audio.original_name,
            source="upload",
            duration_sec=audio.duration_sec,
            language=job.options.get("language"),
            model_name="Qwen3-ASR-1.7B",
            model_version=model_version,
            status="processing",
        )
        self.audio_repo.set_transcription_id(audio.id, record.id)
        self.db.commit()

        engine = AsrEngineManager.get_engine()
        t0 = time.monotonic()
        try:
            raw = await engine.generate(
                prompt=_build_asr_prompt(audio.storage_path, job.options)
            )
        except Exception as e:
            err_name = type(e).__name__
            self.tx_repo.mark_failed(record.id, error_message=f"{err_name}: {e}")
            self.db.commit()
            if "Cuda" in err_name or "CUDA" in err_name:
                raise AsrCudaError(details={"error": str(e)}) from e
            raise AsrInferenceFailedError(details={"error": str(e)}) from e

        duration = time.monotonic() - t0
        text, ts = _parse_vllm_output(raw)
        return_timestamps = job.options.get("return_timestamps", True)
        self.tx_repo.mark_completed(
            record.id,
            transcript_text=text,
            timestamps=ts if return_timestamps else None,
            processing_duration_sec=duration,
        )
        self.db.commit()
        logger.info("transcription completed", transcription_id=record.id, duration_ms=duration * 1000)
        return TranscribeOutcome(
            transcription_id=record.id,
            text=text,
            timestamps=ts if return_timestamps else None,
            duration_sec=audio.duration_sec,
            processing_duration_sec=duration,
            model_version=model_version,
            language=job.options.get("language"),
        )
```

- [ ] **Step 3：撰寫 `tests/unit/test_asr_transcriber.py`**

```python
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

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
    AsrEngineManager.set_engine_for_test(
        _MockEngine({"text": "你好世界", "timestamps": [{"text": "你好", "start": 0.0, "end": 0.5}]}),
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
    AsrEngineManager.set_engine_for_test(_MockEngine(ValueError("bad output")), model_version="MOCK")
    t = Transcriber(db_session, seed_api_key, max_duration_sec=1200)
    with pytest.raises(AsrInferenceFailedError):
        await t.run(AsrJob(audio_file_id=audio_id, api_key_id=seed_api_key, options={}))
```

- [ ] **Step 4：執行測試**

```bash
pytest tests/unit/test_asr_transcriber.py -v
```

預期：5 個測試 PASS。

- [ ] **Step 5：Commit**

```bash
git add backend/app/repositories/transcription.py backend/app/services/asr/transcriber.py backend/tests/unit/test_asr_transcriber.py
git commit -m "feat(asr): 加入 Transcriber 編排與 TranscriptionRepository"
```

---

## Task 4.4：Consumer 背景 task 與 future 等待

**Files:**
- Create: `backend/app/services/asr/consumer.py`
- Create: `backend/tests/unit/test_asr_consumer.py`

- [ ] **Step 1：撰寫 `app/services/asr/consumer.py`**

```python
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
            except (asyncio.CancelledError, Exception):
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


async def wait_for_job(job: AsrJob, timeout: float) -> int:
    """等待 consumer 完成，回傳 transcription_id。"""
    if job.future is None:
        raise RuntimeError("AsrJob.future 未設定")
    try:
        return await asyncio.wait_for(job.future, timeout=timeout)
    except TimeoutError as e:
        raise AsrRequestTimeoutError(details={"job_id": job.job_id, "timeout_sec": timeout}) from e
```

- [ ] **Step 2：撰寫 `tests/unit/test_asr_consumer.py`**

```python
import asyncio

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.core.exceptions import AsrRequestTimeoutError
from app.repositories.audio_file import AudioFileRepository
from app.services.asr.consumer import AsrConsumer, wait_for_job
from app.services.asr.engine import AsrEngineManager
from app.services.asr.queue import AsrJob, AsyncioQueueBackend, QueuePriority


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
    # 注入測試用 session factory
    from app.deps import db as deps_db

    engine = db_session.bind.engine  # type: ignore[union-attr]
    factory = sessionmaker(bind=engine, future=True, expire_on_commit=False)
    monkeypatch.setattr(deps_db, "get_session_factory", lambda: factory)

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
```

- [ ] **Step 3：執行測試**

```bash
pytest tests/unit/test_asr_consumer.py -v
```

預期：2 個測試 PASS。

- [ ] **Step 4：Commit**

```bash
git add backend/app/services/asr/consumer.py backend/tests/unit/test_asr_consumer.py
git commit -m "feat(asr): 加入 AsrConsumer 背景 task 與 wait_for_job 介面"
```

---

## Task 4.5：ASR schemas 與 transcribe 路由

**Files:**
- Create: `backend/app/schemas/asr.py`
- Create: `backend/app/routers/asr.py`
- Modify: `backend/app/services/asr/__init__.py`

- [ ] **Step 1：撰寫 `app/schemas/asr.py`**

```python
from typing import Any

from pydantic import BaseModel, Field


class TranscribeOptions(BaseModel):
    model: str | None = None
    language: str | None = None
    return_timestamps: bool = True

    # Phase 1 接收但忽略（會出現在回應 warnings 內）
    diarization: bool | None = None
    post_processing: bool | None = None
    denoise_enabled: bool | None = None
    nec_enabled: bool | None = None
    punctuation_enabled: bool | None = None
    hotword_group_ids: list[int] | None = None
    vad_enabled: bool = True


class Timestamp(BaseModel):
    text: str
    start: float
    end: float


class TranscribeData(BaseModel):
    transcription_id: int
    audio_file_id: int
    text: str
    timestamps: list[Timestamp] | None = None
    language: str | None = None
    duration_sec: float
    processing_duration_sec: float
    model_version: str
    resampling_warning: bool
    vad_segments_count: int
    warnings: list[str] = Field(default_factory=list)


_UNSUPPORTED_FIELDS = (
    "diarization",
    "post_processing",
    "denoise_enabled",
    "nec_enabled",
    "punctuation_enabled",
    "hotword_group_ids",
)


def collect_unsupported_warnings(options: TranscribeOptions) -> list[str]:
    warnings: list[str] = []
    for field in _UNSUPPORTED_FIELDS:
        value = getattr(options, field, None)
        if value not in (None, False, []):
            warnings.append(f"Phase 1 不支援 {field}，已忽略（將在後續 Phase 啟用）")
    if options.model and options.model != "":
        warnings.append("Phase 1 model 參數已忽略，使用啟動載入的 ASR_MODEL")
    return warnings
```

- [ ] **Step 2：撰寫 `app/routers/asr.py`**

```python
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import structlog
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile

from app.core.config import Settings, get_settings
from app.core.exceptions import AudioFileTooLargeError, ValidationFailedError
from app.core.response import success
from app.deps.auth import require_scope
from app.deps.db import get_db
from app.models import ApiKey
from app.repositories.audio_file import AudioFileRepository
from app.schemas.asr import (
    Timestamp,
    TranscribeData,
    TranscribeOptions,
    collect_unsupported_warnings,
)
from app.schemas.common import ResponseEnvelope
from app.services.asr.consumer import wait_for_job
from app.services.asr.queue import AsrJob, QueueBackend, QueuePriority
from app.services.audio import (
    FireRedVADService,
    resample_to_16k_mono,
    store_upload,
    verify_mime,
)
from sqlalchemy.orm import Session

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/asr", tags=["asr"])


def get_queue(request: Request) -> QueueBackend:
    """從 app.state 取得當前 QueueBackend 實例。"""
    queue: QueueBackend | None = getattr(request.app.state, "asr_queue", None)
    if queue is None:
        raise RuntimeError("asr_queue 未在 app.state 設定（lifespan 未啟動？）")
    return queue


@router.post("/transcribe", response_model=ResponseEnvelope[TranscribeData])
async def transcribe(
    request: Request,
    file: UploadFile = File(...),
    options_json: str = Form("{}"),
    api_key: ApiKey = Depends(require_scope("asr:write")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ResponseEnvelope[TranscribeData]:
    queue = get_queue(request)

    # 解析 options
    try:
        options = TranscribeOptions.model_validate_json(options_json)
    except Exception as e:
        raise ValidationFailedError(details={"options_json": str(e)}) from e

    warnings = collect_unsupported_warnings(options)

    # 讀取 bytes
    raw_bytes = await file.read()
    if len(raw_bytes) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise AudioFileTooLargeError(
            details={"limit_mb": settings.MAX_UPLOAD_SIZE_MB, "actual_bytes": len(raw_bytes)}
        )

    # 預處理
    mime, ext = verify_mime(raw_bytes, settings.supported_formats_list)
    audio = store_upload(
        db=db,
        api_key_id=api_key.id,
        raw_bytes=raw_bytes,
        original_name=file.filename or f"upload.{ext}",
        canonical_ext=ext,
        verified_mime=mime,
        storage_dir=settings.AUDIO_STORAGE_DIR,
    )
    db.commit()

    resample = await resample_to_16k_mono(
        Path(audio.storage_path),
        settings.AUDIO_STORAGE_DIR / "processed",
    )
    AudioFileRepository(db, api_key.id).update_after_resample(
        audio.id,
        original_sample_rate=resample.original_sample_rate,
        duration_sec=resample.duration_sec,
    )
    db.commit()

    vad_segments = await FireRedVADService.detect_speech(resample.output_path)

    # 入佇列等待
    job = AsrJob(
        audio_file_id=audio.id,
        api_key_id=api_key.id,
        options=options.model_dump(),
        future=asyncio.get_event_loop().create_future(),
    )
    await queue.enqueue(job, QueuePriority.BATCH)
    transcription_id = await wait_for_job(job, timeout=settings.ASR_REQUEST_TIMEOUT_SEC)

    # 讀取結果
    from app.repositories.transcription import TranscriptionRepository

    rec = TranscriptionRepository(db, api_key.id).get(transcription_id)
    if rec is None:
        raise ValidationFailedError(message="transcription_id 不存在")

    timestamps = (
        [Timestamp(**t) for t in rec.timestamps] if rec.timestamps else None
    )
    return success(
        TranscribeData(
            transcription_id=rec.id,
            audio_file_id=audio.id,
            text=rec.transcript_text or "",
            timestamps=timestamps,
            language=rec.language,
            duration_sec=rec.duration_sec or 0.0,
            processing_duration_sec=rec.processing_duration_sec or 0.0,
            model_version=rec.model_version,
            resampling_warning=resample.resampling_warning,
            vad_segments_count=len(vad_segments),
            warnings=warnings,
        )
    )
```

- [ ] **Step 3：補完 `app/services/asr/__init__.py`**

```python
from app.services.asr.consumer import AsrConsumer, wait_for_job
from app.services.asr.engine import AsrEngineManager, compute_model_version
from app.services.asr.queue import (
    AsrJob,
    AsyncioQueueBackend,
    QueueBackend,
    QueuePriority,
)
from app.services.asr.transcriber import TranscribeOutcome, Transcriber

__all__ = [
    "AsrConsumer",
    "AsrEngineManager",
    "AsrJob",
    "AsyncioQueueBackend",
    "QueueBackend",
    "QueuePriority",
    "TranscribeOutcome",
    "Transcriber",
    "compute_model_version",
    "wait_for_job",
]
```

- [ ] **Step 4：Commit（測試於 Task 4.6 整合）**

```bash
git add backend/app/schemas/asr.py backend/app/routers/asr.py backend/app/services/asr/__init__.py
git commit -m "feat(asr): 加入 transcribe 路由與 TranscribeOptions / TranscribeData schema"
```

---

## Task 4.6：transcribe 端點整合測試（mock vLLM）

**Files:**
- Create: `backend/tests/integration/test_asr_transcribe.py`

- [ ] **Step 1：撰寫整合測試**

```python
import asyncio
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.core.security import derive_hmac_key, hash_token, lookup_prefix
from app.deps.db import get_db
from app.routers.asr import router as asr_router
from app.services.asr.consumer import AsrConsumer
from app.services.asr.engine import AsrEngineManager
from app.services.asr.queue import AsyncioQueueBackend
from app.services.audio.vad import FireRedVADService

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "audio"


class _MockEngine:
    async def generate(self, **kwargs):  # type: ignore[no-untyped-def]
        return {"text": "你好世界，這是測試辨識結果。", "timestamps": None}

    async def abort_all(self) -> None:
        return None


class _FakeVadModel:
    def infer(self, wav_path: str) -> list[tuple[float, float]]:
        return [(0.0, 1.0)]


@pytest.fixture
def app_with_asr(
    db_session: Session, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> tuple[FastAPI, str]:
    monkeypatch.setenv("API_KEY", "smoke-bootstrap")
    monkeypatch.setenv("DATABASE_URL", str(db_session.bind.engine.url))
    monkeypatch.setenv("DB_PASSWORD", "test")
    monkeypatch.setenv("THIRD_PARTY_LICENSE_ACK", "true")
    monkeypatch.setenv("AUDIO_STORAGE_DIR", str(tmp_path))
    monkeypatch.setenv("SUPPORTED_AUDIO_FORMATS", "wav,mp3")
    monkeypatch.setenv("MAX_UPLOAD_SIZE_MB", "100")

    from app.core.config import get_settings
    from app.deps.db import get_engine, get_session_factory

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()

    # 建立有效 token
    raw_token = "real-test-token-x"
    hmac_key = derive_hmac_key("smoke-bootstrap")
    db_session.execute(text("TRUNCATE api_keys, audio_files, transcriptions, audit_logs CASCADE"))
    db_session.execute(
        text(
            "INSERT INTO api_keys (key_hash, lookup_prefix, name, scopes) "
            "VALUES (:h, :p, 't', '{asr:write}')"
        ),
        {"h": hash_token(raw_token), "p": lookup_prefix(raw_token, hmac_key)},
    )
    db_session.commit()

    # 注入 mock engine / VAD
    AsrEngineManager.set_engine_for_test(_MockEngine(), model_version="MOCK@TEST")
    FireRedVADService.set_model(_FakeVadModel())

    # 建立 FastAPI app（僅含 ASR 路由）
    from app.middleware import register_exception_handlers

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(asr_router)
    app.dependency_overrides[get_db] = lambda: db_session

    # 啟動 consumer
    queue = AsyncioQueueBackend(realtime_max=5, batch_max=5)
    app.state.asr_queue = queue
    consumer = AsrConsumer(queue, max_duration_sec=1200)
    app.state.asr_consumer = consumer

    factory = sessionmaker(bind=db_session.bind.engine, future=True, expire_on_commit=False)
    monkeypatch.setattr("app.services.asr.consumer.get_session_factory", lambda: factory)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(consumer.start())

    yield app, raw_token

    loop.run_until_complete(consumer.stop())
    loop.close()
    AsrEngineManager.set_engine_for_test(None)
    FireRedVADService.set_model(None)


def test_transcribe_endpoint_returns_text(app_with_asr) -> None:
    app, token = app_with_asr
    with TestClient(app) as client:
        with (FIXTURES / "valid_16k_mono.wav").open("rb") as f:
            resp = client.post(
                "/api/v1/asr/transcribe",
                files={"file": ("a.wav", f, "audio/wav")},
                data={"options_json": json.dumps({"language": "zh-TW", "return_timestamps": False})},
                headers={"Authorization": f"Bearer {token}"},
            )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["text"] == "你好世界，這是測試辨識結果。"
    assert body["data"]["model_version"] == "MOCK@TEST"
    assert body["data"]["resampling_warning"] is False


def test_transcribe_warns_unsupported_options(app_with_asr) -> None:
    app, token = app_with_asr
    with TestClient(app) as client:
        with (FIXTURES / "valid_16k_mono.wav").open("rb") as f:
            resp = client.post(
                "/api/v1/asr/transcribe",
                files={"file": ("a.wav", f, "audio/wav")},
                data={"options_json": json.dumps({"diarization": True, "nec_enabled": True})},
                headers={"Authorization": f"Bearer {token}"},
            )
    assert resp.status_code == 200
    body = resp.json()
    assert any("diarization" in w for w in body["data"]["warnings"])
    assert any("nec_enabled" in w for w in body["data"]["warnings"])


def test_transcribe_8k_audio_sets_resampling_warning(app_with_asr) -> None:
    app, token = app_with_asr
    with TestClient(app) as client:
        with (FIXTURES / "valid_8k_mono.wav").open("rb") as f:
            resp = client.post(
                "/api/v1/asr/transcribe",
                files={"file": ("a.wav", f, "audio/wav")},
                data={"options_json": "{}"},
                headers={"Authorization": f"Bearer {token}"},
            )
    assert resp.status_code == 200
    assert resp.json()["data"]["resampling_warning"] is True


def test_transcribe_rejects_zip_disguised_as_wav(app_with_asr) -> None:
    app, token = app_with_asr
    with TestClient(app) as client:
        with (FIXTURES / "fake_extension.wav.zip").open("rb") as f:
            resp = client.post(
                "/api/v1/asr/transcribe",
                files={"file": ("a.wav", f, "audio/wav")},
                data={"options_json": "{}"},
                headers={"Authorization": f"Bearer {token}"},
            )
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "AUDIO_MIME_INVALID"


def test_transcribe_unauthenticated_returns_401(app_with_asr) -> None:
    app, _ = app_with_asr
    with TestClient(app) as client:
        with (FIXTURES / "valid_16k_mono.wav").open("rb") as f:
            resp = client.post(
                "/api/v1/asr/transcribe",
                files={"file": ("a.wav", f, "audio/wav")},
                data={"options_json": "{}"},
            )
    assert resp.status_code == 401
```

- [ ] **Step 2：執行測試**

```bash
pytest tests/integration/test_asr_transcribe.py -v
```

預期：5 個測試 PASS。

- [ ] **Step 3：Commit**

```bash
git add backend/tests/integration/test_asr_transcribe.py
git commit -m "test(asr): 加入 transcribe 端點端到端整合測試（mock vLLM）"
```

---

## Task 4.7：main.py 串接 lifespan（含 engine / consumer）

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/tests/integration/test_app.py`（補一個 ASR 路由註冊測試）

- [ ] **Step 1：修改 `app/main.py`**

完整覆寫如下：

```python
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging, get_logger
from app.core.startup_checks import run_startup_checks
from app.deps.db import get_session_factory
from app.middleware import (
    idempotency_middleware,
    prometheus_middleware,
    rate_limit_middleware,
    register_exception_handlers,
    request_id_middleware,
    tracing_middleware,
)
from app.routers.asr import router as asr_router
from app.routers.health import router as health_router
from app.services.asr.consumer import AsrConsumer
from app.services.asr.engine import AsrEngineManager
from app.services.asr.queue import AsyncioQueueBackend
from app.services.audio.vad import FireRedVADService
from app.services.bootstrap import bootstrap_admin_key


def _configure_app(settings: Settings) -> FastAPI:
    configure_logging(level=settings.LOG_LEVEL, json_format=settings.LOG_FORMAT == "json")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        logger = get_logger("startup")
        logger.info("backend lifespan start", env=settings.ENV)
        run_startup_checks(settings)
        with get_session_factory()() as db:
            bootstrap_admin_key(db, settings)

        # 載入 VAD（Phase 1 必載）
        if settings.VAD_ENABLED:
            try:
                FireRedVADService.load(settings.VAD_MODEL_PATH)
            except RuntimeError as e:
                if settings.ENV == "production":
                    raise
                logger.warning("VAD load failed (development tolerated)", error=str(e))

        # 載入 vLLM
        try:
            await AsrEngineManager.initialize(settings)
        except RuntimeError as e:
            if settings.ENV == "production":
                raise
            logger.warning("vLLM initialize skipped (development)", error=str(e))

        # 啟動 ASR 佇列與 consumer
        queue = AsyncioQueueBackend(
            realtime_max=settings.QUEUE_REALTIME_MAX_SIZE,
            batch_max=settings.QUEUE_BATCH_MAX_SIZE,
        )
        app.state.asr_queue = queue
        consumer = AsrConsumer(queue, max_duration_sec=settings.ASR_AUDIO_MAX_DURATION_SEC)
        await consumer.start()
        app.state.asr_consumer = consumer

        yield

        await consumer.stop()
        await AsrEngineManager.shutdown()
        logger.info("backend lifespan stop")

    app = FastAPI(
        title="Qwen3-ASR API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.OPENAPI_DOCS_ENABLED else None,
        redoc_url=None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.middleware("http")(idempotency_middleware)
    app.middleware("http")(rate_limit_middleware)
    app.middleware("http")(prometheus_middleware)
    app.middleware("http")(tracing_middleware)
    app.middleware("http")(request_id_middleware)

    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(asr_router)
    return app


def create_app() -> FastAPI:
    return _configure_app(get_settings())


app = create_app()
```

- [ ] **Step 2：補一個確認路由註冊的測試**

修改 `tests/integration/test_app.py`，在現有測試後加入：

```python
def test_asr_route_registered(configured_app) -> None:
    paths = [route.path for route in configured_app.routes]
    assert "/api/v1/asr/transcribe" in paths
```

- [ ] **Step 3：執行整合測試**

```bash
pytest tests/integration/test_app.py -v
```

預期：先前 4 個測試 + 新測試共 5 個 PASS。

- [ ] **Step 4：Commit**

```bash
git add backend/app/main.py backend/tests/integration/test_app.py
git commit -m "feat(asr): 在 lifespan 整合 vLLM 載入、ASR 佇列與 consumer"
```

---

## Task 4.8：Linux GPU smoke 腳本

**Files:**
- Create: `backend/scripts/smoke_asr.sh`

- [ ] **Step 1：撰寫 `backend/scripts/smoke_asr.sh`**

```bash
#!/usr/bin/env bash
# Linux + NVIDIA GPU 環境執行的 ASR 端到端 manual smoke。
# 使用方式：
#   export ASR_SMOKE_TOKEN="<bootstrap API key>"
#   export ASR_SMOKE_HOST="http://localhost:8000"
#   ./scripts/smoke_asr.sh tests/fixtures/audio/valid_16k_mono.wav
set -euo pipefail

HOST="${ASR_SMOKE_HOST:-http://localhost:8000}"
TOKEN="${ASR_SMOKE_TOKEN:?need bootstrap admin token}"
AUDIO_FILE="${1:?usage: $0 <audio_path>}"

if [ ! -f "$AUDIO_FILE" ]; then
  echo "audio file not found: $AUDIO_FILE" >&2
  exit 2
fi

echo "smoke: POST $HOST/api/v1/asr/transcribe with $AUDIO_FILE"
response=$(curl -fsS -X POST "$HOST/api/v1/asr/transcribe" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@$AUDIO_FILE" \
  -F 'options_json={"language":"zh-TW","return_timestamps":true}')

echo "$response" | jq '{
  success,
  text: .data.text,
  duration_sec: .data.duration_sec,
  processing_duration_sec: .data.processing_duration_sec,
  model_version: .data.model_version,
  resampling_warning: .data.resampling_warning,
  vad_segments_count: .data.vad_segments_count,
  warnings: .data.warnings
}'

success=$(echo "$response" | jq -r '.success')
if [ "$success" != "true" ]; then
  echo "smoke failed: $response" >&2
  exit 1
fi
echo "smoke OK"
```

- [ ] **Step 2：設定執行權限（Linux）**

```bash
chmod +x backend/scripts/smoke_asr.sh
```

> Windows 端可跳過此步驟；實際在 GPU 主機上跑時設定。

- [ ] **Step 3：Commit**

```bash
git add backend/scripts/smoke_asr.sh
git commit -m "feat(asr): 加入 Linux GPU smoke 腳本"
```

---

## Task 4.9：M4 整合驗收

**Files:**（無新檔案）

- [ ] **Step 1：本機跑完整 pytest 並驗證覆蓋率**

```bash
cd backend
pytest --cov=app --cov-report=term --cov-report=html
```

預期：所有測試 PASS，覆蓋率 ≥ 70%。

- [ ] **Step 2：以 docker compose 啟動全堆疊（CPU 階段；vLLM 部分會被 development 容忍）**

```bash
cd D:\Qwen_asr
Copy-Item .env.example .env
# 修改 .env：API_KEY / DB_PASSWORD 改成強隨機
docker compose up -d
Start-Sleep -Seconds 30
```

- [ ] **Step 3：以 mock 不可行（CPU 不會有 vLLM），但驗證 health 與認證**

```bash
$token = "<以 .env 中的 API_KEY 替換>"
curl http://localhost:8000/health
curl -H "Authorization: Bearer $token" http://localhost:8000/readiness
```

預期：兩端點皆 200。

- [ ] **Step 4：將 plan 推給 GPU 主機進行真實 smoke（Linux + NVIDIA GPU 環境）**

在 GPU 主機（或 SSH 連線）執行：

```bash
git clone <repo-url> qwen_asr
cd qwen_asr
cp .env.example .env
# 編輯 .env：API_KEY, DB_PASSWORD, INSTALL_GPU_DEPS=true
docker compose build asr-backend --build-arg INSTALL_GPU_DEPS=true
docker compose up -d

# 等待模型載入（首次可能 5-15 分鐘下載權重）
docker compose logs -f asr-backend  # 看到 "ASR engine initialized" 後 Ctrl+C

# 下載小型測試音檔或使用 fixture
./backend/scripts/smoke_asr.sh backend/tests/fixtures/audio/valid_16k_mono.wav
```

預期：smoke 腳本印出 `success: true`、`text`、`processing_duration_sec`，並 exit 0。

- [ ] **Step 5：清理 CPU 環境**

```bash
docker compose down -v
Remove-Item .env
```

- [ ] **Step 6：Push**

```bash
git push origin main
```

---

## Self-Review

**1. Spec coverage（對照設計文件第 2.5、6 段）：**

| 設計章節 | 對應 Task |
|---------|----------|
| 2.5 M4 工作項目 (1)–(7) | T4.1 / T4.2 / T4.3+T4.4 / T4.5 / T4.5 / T4.6 / T4.8 |
| 6.1 vLLM 啟動載入 | T4.2、T4.7 |
| 6.2 佇列抽象層 | T4.1 |
| 6.3 Phase 1 模式：同步 API + 內部 Queue | T4.4 + T4.5 |
| 6.4 Transcriber 編排 | T4.3 |
| 6.5 端點 schema 與實作 | T4.5 |
| 6.6 雙模型策略對 Phase 1 的影響 | T4.2（model_version 寫入） + T4.3（讀取）|
| 6.7 Phase 1 未實作的 ASR 相關端點 | 不在範圍（僅文件聲明）|
| 6.8 錯誤碼擴充 | M2 Task 2.2 已建立全部錯誤碼 |
| 6.9 整合測試策略 | T4.6 + T4.8 |
| 2.5 M4 DoD 條件 1–8 | T4.6（CI mock）+ T4.8（GPU smoke）+ T4.9 |

**2. Placeholder scan：** 已搜尋禁用詞，無命中。`firered_vad` / `vllm` import 為實際的延伸點（試圖 import，失敗給出可診斷錯誤），非 placeholder。

**3. Type consistency：**
- `AsrJob.future` 在 queue.py / consumer.py / asr.py 一致使用 `asyncio.Future[int]`
- `AsrEngineManager.set_engine_for_test()` 簽章在 4 個測試檔皆一致呼叫
- `_MockEngine.generate` 模式（accept **kwargs，return dict / raise）在 4.2 / 4.3 / 4.4 / 4.6 一致
- `Transcriber.run(job)` 回傳 `TranscribeOutcome` 在 transcriber.py / consumer.py / asr.py 一致
- `compute_model_version()` 簽章在 engine.py、test 一致

---

## Execution Handoff

M4 plan 完成。M1–M4 四份 plan 已全部就緒，下一步進入 Subagent-Driven Execution。

執行起點：M1（`docs/superpowers/plans/2026-05-16-phase1-m1-infrastructure.md`）。
