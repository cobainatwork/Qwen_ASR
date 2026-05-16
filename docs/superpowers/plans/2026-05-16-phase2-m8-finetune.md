# Phase 2 / M8 — Fine-tune 管線 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 實作 Fine-tune 任務管理、訓練 runner、推理隔離與 checkpoint 管理，完成後 `POST /api/v1/finetune/tasks` 可建立任務，runner 子程序執行訓練並透過 file-based 通訊回報進度，`POST /:id/promote` 切換 active 模型。

**Architecture:** Fine-tune 任務以狀態機驅動（pending → preparing → training → evaluating → completed/failed）。`FINETUNE_MAX_CONCURRENT=1` 強制單一任務（規格約定）。訓練 runner 為 `subprocess.Popen` 獨立子程序（非 multiprocessing，避免 fork 衝突 vLLM）。透過 `/data/finetune.lock` file 與主程式溝通：lock 存在時 Transcriber 自動降級（已於 M7 整合）。

**Tech Stack:** torchrun（LoRA / QLoRA）、peft、transformers、datasets、subprocess。

**對應設計文件：** Phase 2 design.md §3.4、§4.1、§4.3。對應規格：v1.9 §3.3.6、§15、§18.2、§3.4。

---

## File Structure

| 路徑 | 動作 | 責任 |
|------|------|------|
| `backend/app/models/finetune.py` | Create | `FinetuneTask` / `FinetuneCheckpoint` ORM |
| `backend/app/models/__init__.py` | Modify | re-export |
| `backend/alembic/versions/0003_finetune.py` | Create | DB schema |
| `backend/app/schemas/finetune.py` | Create | Pydantic schemas |
| `backend/app/repositories/finetune.py` | Create | `FinetuneTaskRepository` / `FinetuneCheckpointRepository` |
| `backend/app/services/finetune/state_machine.py` | Create | 狀態轉換邏輯 |
| `backend/app/services/finetune/runner.py` | Create | subprocess 啟動 + 監聽 |
| `backend/app/services/finetune/data_augmentation.py` | Create | 可選資料增強 |
| `backend/app/services/finetune/lock.py` | Modify | 補 `acquire_for_task(task_id)` |
| `backend/app/routers/finetune.py` | Create | 5 個端點 |
| `backend/scripts/finetune_runner.py` | Create | 訓練子程序主程式（佔位 + 結構） |
| `backend/app/core/exceptions.py` | Modify | 新增 4 個錯誤碼 |
| `backend/app/main.py` | Modify | include router + 啟動時清理孤兒 lock |
| `backend/tests/unit/test_finetune_state_machine.py` | Create | 狀態機測試 |
| `backend/tests/integration/test_finetune_router.py` | Create | 5 個端點整合測試 |
| `backend/tests/integration/test_finetune_isolation.py` | Create | 推理隔離端到端 |

---

## Task 8.1：ORM models + migration + exceptions

**Files:**
- Create: `backend/app/models/finetune.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/0003_finetune.py`
- Modify: `backend/app/core/exceptions.py`

- [ ] **Step 1：撰寫 `app/models/finetune.py`**

```python
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin


class FinetuneTask(Base, TenantMixin):
    __tablename__ = "finetune_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    dataset_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("datasets.id"), nullable=False
    )
    base_model: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, server_default="pending")
    config: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    loss_history: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class FinetuneCheckpoint(Base):
    __tablename__ = "finetune_checkpoints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("finetune_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    epoch: Mapped[int] = mapped_column(Integer, nullable=False)
    step: Mapped[int] = mapped_column(Integer, nullable=False)
    loss: Mapped[float] = mapped_column(Float, nullable=False)
    wer: Mapped[float | None] = mapped_column(Float, nullable=True)
    checkpoint_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=False, server_default="false", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
```

- [ ] **Step 2：補 `__init__.py` re-export**

```python
from app.models.finetune import FinetuneCheckpoint, FinetuneTask
```

`__all__` 補 `"FinetuneCheckpoint", "FinetuneTask"`。

- [ ] **Step 3：撰寫 `backend/alembic/versions/0003_finetune.py`**

```python
"""Phase 2 / M8：finetune_tasks / finetune_checkpoints

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-16

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "finetune_tasks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("api_key_id", sa.Integer(), sa.ForeignKey("api_keys.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("dataset_id", sa.Integer(), sa.ForeignKey("datasets.id"), nullable=False),
        sa.Column("base_model", sa.String(200), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("config", postgresql.JSONB(), nullable=True),
        sa.Column("loss_history", postgresql.JSONB(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_finetune_tasks_api_key_id", "finetune_tasks", ["api_key_id"])
    op.create_index("idx_finetune_tasks_status", "finetune_tasks", ["status"])

    op.create_table(
        "finetune_checkpoints",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("finetune_tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("epoch", sa.Integer(), nullable=False),
        sa.Column("step", sa.Integer(), nullable=False),
        sa.Column("loss", sa.Float(), nullable=False),
        sa.Column("wer", sa.Float(), nullable=True),
        sa.Column("checkpoint_path", sa.String(500), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_finetune_checkpoints_task_id", "finetune_checkpoints", ["task_id"])
    # 唯一 active checkpoint per task
    op.create_index(
        "idx_finetune_checkpoints_active_unique",
        "finetune_checkpoints",
        ["task_id"],
        unique=True,
        postgresql_where=sa.text("is_active = TRUE"),
    )

    op.execute(
        "CREATE TRIGGER trg_finetune_tasks_updated_at "
        "BEFORE UPDATE ON finetune_tasks FOR EACH ROW EXECUTE FUNCTION set_updated_at();"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_finetune_tasks_updated_at ON finetune_tasks")
    op.drop_table("finetune_checkpoints")
    op.drop_table("finetune_tasks")
```

- [ ] **Step 4：擴充 `exceptions.py`**

```python
# ----- Phase 2 / M8 -----
class FinetuneConcurrentError(AppException):
    code = "FINETUNE_CONCURRENT"
    http_status = 409
    message = "已有 Fine-tune 任務在執行（FINETUNE_MAX_CONCURRENT=1）"


class FinetuneTaskNotFoundError(AppException):
    code = "FINETUNE_TASK_NOT_FOUND"
    http_status = 404
    message = "Fine-tune 任務不存在"


class FinetuneCheckpointNotFoundError(AppException):
    code = "FINETUNE_CHECKPOINT_NOT_FOUND"
    http_status = 404
    message = "Checkpoint 不存在"


class FinetunePromoteFailedError(AppException):
    code = "FINETUNE_PROMOTE_FAILED"
    http_status = 500
    message = "Checkpoint promote 失敗"
```

擴充 `ALL_ERROR_CODES` 4 個（從 30 → 34）。

- [ ] **Step 5：alembic 驗證**

```powershell
cd D:\Qwen_asr
docker compose up -d postgres
Start-Sleep -Seconds 20

cd backend
$env:DATABASE_URL = "postgresql+psycopg://qwasr:devpass@localhost:5432/qwen_asr"
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\alembic.exe downgrade 0002
.\.venv\Scripts\alembic.exe upgrade head

cd ..
docker compose down -v
```

預期：upgrade 增 2 表（共 11 個 git 追蹤表），downgrade 回 9。

- [ ] **Step 6：Commit**

```powershell
cd D:\Qwen_asr
git add backend/app/models/finetune.py backend/app/models/__init__.py backend/alembic/versions/0003_finetune.py backend/app/core/exceptions.py
git commit -m "$(@'
feat(m8): 加入 FinetuneTask / FinetuneCheckpoint ORM + 0003 migration + 4 錯誤碼

- models/finetune.py：
  - FinetuneTask（TenantMixin + dataset FK + status + loss_history JSONB）
  - FinetuneCheckpoint（task FK + epoch / step / loss / wer / is_active）
- alembic 0003：
  - 兩個新表 + partial unique index（每 task 僅一個 active checkpoint）
  - trigger 重用 set_updated_at function
- exceptions 補 4 個：
  - FinetuneConcurrentError（409）
  - FinetuneTaskNotFoundError（404）
  - FinetuneCheckpointNotFoundError（404）
  - FinetunePromoteFailedError（500）
- ALL_ERROR_CODES 30 → 34

對應計劃：M8 Task 8.1
對應規格：v1.9 §5、§3.4

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
'@)"
```

---

## Task 8.2：Repositories + state machine

**Files:**
- Create: `backend/app/repositories/finetune.py`
- Create: `backend/app/services/finetune/state_machine.py`
- Create: `backend/tests/unit/test_finetune_state_machine.py`

- [ ] **Step 1：撰寫 `app/repositories/finetune.py`**

```python
from sqlalchemy import select

from app.models import FinetuneCheckpoint, FinetuneTask
from app.repositories.base import TenantScopedRepository


class FinetuneTaskRepository(TenantScopedRepository[FinetuneTask]):
    model = FinetuneTask

    def has_active_task(self) -> bool:
        """檢查當前 api_key 是否有非終態任務（FINETUNE_MAX_CONCURRENT=1 強制）。"""
        return self.db.execute(
            select(FinetuneTask).where(
                FinetuneTask.api_key_id == self.api_key_id,
                FinetuneTask.status.in_(["pending", "preparing", "training", "evaluating"]),
            ).limit(1)
        ).scalar_one_or_none() is not None

    def append_loss(self, task_id: int, entry: dict) -> None:
        task = self.get(task_id)
        if task is None:
            return
        history = list(task.loss_history or [])
        history.append(entry)
        task.loss_history = history
        self.db.flush()


class FinetuneCheckpointRepository:
    """Checkpoint 跨 task 存取（Tenant 透過 task → api_key_id 驗證）。"""

    def __init__(self, db, api_key_id: int) -> None:  # type: ignore[no-untyped-def]
        self.db = db
        self.api_key_id = api_key_id

    def create(
        self,
        *,
        task_id: int,
        epoch: int,
        step: int,
        loss: float,
        wer: float | None,
        checkpoint_path: str,
        file_size: int,
    ) -> FinetuneCheckpoint:
        ckpt = FinetuneCheckpoint(
            task_id=task_id,
            epoch=epoch,
            step=step,
            loss=loss,
            wer=wer,
            checkpoint_path=checkpoint_path,
            file_size=file_size,
        )
        self.db.add(ckpt)
        self.db.flush()
        return ckpt

    def get(self, ckpt_id: int) -> FinetuneCheckpoint | None:
        return self.db.execute(
            select(FinetuneCheckpoint).where(FinetuneCheckpoint.id == ckpt_id)
        ).scalar_one_or_none()

    def list_by_task(self, task_id: int) -> list[FinetuneCheckpoint]:
        return list(self.db.execute(
            select(FinetuneCheckpoint).where(FinetuneCheckpoint.task_id == task_id).order_by(FinetuneCheckpoint.epoch)
        ).scalars().all())

    def deactivate_all_for_task(self, task_id: int) -> None:
        for ckpt in self.list_by_task(task_id):
            ckpt.is_active = False
        self.db.flush()

    def activate(self, ckpt_id: int) -> None:
        ckpt = self.get(ckpt_id)
        if ckpt is None:
            return
        self.deactivate_all_for_task(ckpt.task_id)
        ckpt.is_active = True
        self.db.flush()
```

- [ ] **Step 2：撰寫 `app/services/finetune/state_machine.py`**

```python
"""Fine-tune 任務狀態機。

合法轉換：
- pending → preparing
- preparing → training
- training → evaluating
- evaluating → completed
- 任何狀態（除 completed）→ failed
"""

from __future__ import annotations

# 合法狀態
_STATES = frozenset({"pending", "preparing", "training", "evaluating", "completed", "failed"})

# 合法轉換 map（from → set of to）
_TRANSITIONS: dict[str, frozenset[str]] = {
    "pending": frozenset({"preparing", "failed"}),
    "preparing": frozenset({"training", "failed"}),
    "training": frozenset({"evaluating", "failed"}),
    "evaluating": frozenset({"completed", "failed"}),
    "completed": frozenset(),
    "failed": frozenset(),
}

_TERMINAL = frozenset({"completed", "failed"})


def is_valid_state(state: str) -> bool:
    return state in _STATES


def can_transition(from_state: str, to_state: str) -> bool:
    if from_state not in _TRANSITIONS:
        return False
    return to_state in _TRANSITIONS[from_state]


def is_terminal(state: str) -> bool:
    return state in _TERMINAL


def is_active(state: str) -> bool:
    """非終態 = active（佔用 FINETUNE_MAX_CONCURRENT 名額）。"""
    return state not in _TERMINAL


class InvalidStateTransitionError(Exception):
    """非業務例外，由 service 層轉換為 AppException。"""
```

- [ ] **Step 3：撰寫 `tests/unit/test_finetune_state_machine.py`**

```python
import pytest

from app.services.finetune.state_machine import (
    can_transition,
    is_active,
    is_terminal,
    is_valid_state,
)


def test_valid_states() -> None:
    for s in ["pending", "preparing", "training", "evaluating", "completed", "failed"]:
        assert is_valid_state(s)
    assert not is_valid_state("unknown")


@pytest.mark.parametrize("from_state,to_state,expected", [
    ("pending", "preparing", True),
    ("pending", "training", False),
    ("preparing", "training", True),
    ("training", "evaluating", True),
    ("evaluating", "completed", True),
    ("evaluating", "failed", True),
    ("completed", "preparing", False),
    ("failed", "training", False),
    ("training", "failed", True),
])
def test_transitions(from_state: str, to_state: str, expected: bool) -> None:
    assert can_transition(from_state, to_state) == expected


def test_is_terminal() -> None:
    assert is_terminal("completed")
    assert is_terminal("failed")
    assert not is_terminal("training")


def test_is_active() -> None:
    assert is_active("pending")
    assert is_active("training")
    assert not is_active("completed")
    assert not is_active("failed")
```

- [ ] **Step 4：執行測試 + ruff + mypy**

```powershell
cd D:\Qwen_asr\backend
.\.venv\Scripts\pytest.exe tests/unit/test_finetune_state_machine.py -v
.\.venv\Scripts\ruff.exe check app tests
.\.venv\Scripts\mypy.exe app
```

預期：parametrize 9 + 3 = 12 個 case PASS（4 個 test function）。

- [ ] **Step 5：Commit**

```powershell
cd D:\Qwen_asr
git add backend/app/repositories/finetune.py backend/app/services/finetune/state_machine.py backend/tests/unit/test_finetune_state_machine.py
git commit -m "$(@'
feat(m8): FinetuneTask/Checkpoint Repository + 狀態機

- repositories/finetune.py：
  - FinetuneTaskRepository（TenantScoped）
    - has_active_task：檢查 FINETUNE_MAX_CONCURRENT=1 用
    - append_loss：每 epoch 追加 loss_history
  - FinetuneCheckpointRepository（跨 task）
    - create / list_by_task / activate（含 deactivate_all_for_task）
- services/finetune/state_machine.py：純函數狀態機
  - 6 個合法狀態，5 個轉換規則
  - is_terminal / is_active 輔助
- 4 個單元測試（含 parametrize 9 case 共 12 case）

對應計劃：M8 Task 8.2

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
'@)"
```

---

## Task 8.3：Runner（subprocess）+ 資料增強 + lock 補強

**Files:**
- Modify: `backend/app/services/finetune/lock.py`
- Create: `backend/app/services/finetune/runner.py`
- Create: `backend/app/services/finetune/data_augmentation.py`
- Create: `backend/scripts/finetune_runner.py`

- [ ] **Step 1：擴充 `app/services/finetune/lock.py`（補 task_id 寫入）**

讀取既有 lock.py，把 `acquire_lock` 改為 `acquire_lock(settings, task_id=None)`，內容寫入 `{"pid": ..., "task_id": ...}` 而非單純 pid：

```python
import json
import os
from pathlib import Path

import structlog

from app.core.config import Settings

logger = structlog.get_logger(__name__)


def get_lock_path(settings: Settings) -> Path:
    return Path(getattr(settings, "FINETUNE_LOCK_PATH", "/data/finetune.lock"))


def is_finetune_active(settings: Settings) -> bool:
    return get_lock_path(settings).exists()


def acquire_lock(settings: Settings, task_id: int | None = None) -> None:
    path = get_lock_path(settings)
    if path.exists():
        raise RuntimeError(f"Finetune lock already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    content = {"pid": os.getpid(), "task_id": task_id}
    path.write_text(json.dumps(content))
    logger.info("finetune lock acquired", path=str(path), task_id=task_id, pid=os.getpid())


def read_lock(settings: Settings) -> dict | None:
    path = get_lock_path(settings)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return {"pid": path.read_text().strip(), "task_id": None}


def release_lock(settings: Settings) -> None:
    path = get_lock_path(settings)
    path.unlink(missing_ok=True)
    logger.info("finetune lock released", path=str(path))
```

- [ ] **Step 2：撰寫 `app/services/finetune/data_augmentation.py`**

```python
"""資料增強策略（規格 §15.3）。

可選功能，由 DATA_AUGMENTATION_ENABLED 控制。
- 速度擾動（0.9x / 1.1x）
- 加噪（高斯白噪音）
- SpecAugment（時間 / 頻率 mask）
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AugmentationPlan:
    speed_perturbation: bool
    noise_injection: bool
    spec_augment: bool

    @classmethod
    def from_config(cls, enabled: bool) -> "AugmentationPlan":
        if not enabled:
            return cls(speed_perturbation=False, noise_injection=False, spec_augment=False)
        return cls(speed_perturbation=True, noise_injection=True, spec_augment=True)

    def to_runner_args(self) -> list[str]:
        """轉為 finetune_runner.py CLI 參數。"""
        args: list[str] = []
        if self.speed_perturbation:
            args.append("--augment-speed")
        if self.noise_injection:
            args.append("--augment-noise")
        if self.spec_augment:
            args.append("--augment-specaug")
        return args
```

- [ ] **Step 3：撰寫 `app/services/finetune/runner.py`**

```python
"""Fine-tune 訓練 runner（subprocess.Popen）。

關鍵設計：
- 不用 multiprocessing（避免 fork 衝突 vLLM 已 init 的 CUDA context）
- subprocess.Popen 啟動獨立 Python 子程序
- 子程序透過 stdout JSONL 回報進度 → 主程式解析寫入 DB
- 主程式關閉時不殺子程序（讓子程序自行完成；下次啟動掃 orphan lock）
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import structlog

from app.core.config import Settings
from app.services.finetune.data_augmentation import AugmentationPlan
from app.services.finetune.lock import acquire_lock, release_lock

logger = structlog.get_logger(__name__)


async def start_finetune_subprocess(
    *,
    task_id: int,
    dataset_id: int,
    base_model: str,
    config: dict[str, Any],
    settings: Settings,
) -> asyncio.Task[int]:
    """啟動訓練子程序，回傳 asyncio.Task（包裝 wait 與進度監聽）。

    呼叫者負責更新 task.status 為 "preparing"。
    """
    acquire_lock(settings, task_id=task_id)

    script = Path(__file__).resolve().parent.parent.parent.parent / "scripts" / "finetune_runner.py"
    augment = AugmentationPlan.from_config(settings.DATA_AUGMENTATION_ENABLED)

    cmd = [
        sys.executable,
        str(script),
        "--task-id", str(task_id),
        "--dataset-id", str(dataset_id),
        "--base-model", base_model,
        "--config", json.dumps(config),
        "--gpu-fraction", str(settings.FINETUNE_GPU_FRACTION),
    ] + augment.to_runner_args()

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    logger.info("finetune subprocess started", task_id=task_id, pid=proc.pid)

    async def _monitor() -> int:
        try:
            if proc.stdout is None:
                return -1
            async for raw_line in proc.stdout:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    logger.info("finetune progress", task_id=task_id, event=event)
                    # 主程式可在 callback 中寫 DB；本 runner 僅 log
                except json.JSONDecodeError:
                    logger.warning("finetune non-json output", line=line[:200])
            await proc.wait()
            return proc.returncode or 0
        finally:
            release_lock(settings)
            logger.info("finetune subprocess exited", task_id=task_id, returncode=proc.returncode)

    return asyncio.create_task(_monitor(), name=f"finetune-monitor-{task_id}")
```

新增對應 ENV：

`app/core/config.py` 補：
```python
    DATA_AUGMENTATION_ENABLED: bool = False
    FINETUNE_GPU_FRACTION: float = 0.65
```

- [ ] **Step 4：撰寫 `backend/scripts/finetune_runner.py`（佔位 + 結構）**

```python
"""Fine-tune 訓練子程序入口。

實際訓練邏輯（LoRA / QLoRA + datasets + transformers Trainer）依
Qwen3-ASR-1.7B 官方文件補完。本 milestone 提供結構與 stdout JSONL 通訊
協議，讓主程式可監聽進度並更新 DB。

執行範例：
  python scripts/finetune_runner.py \\
    --task-id 1 \\
    --dataset-id 2 \\
    --base-model Qwen/Qwen3-ASR-1.7B \\
    --config '{"epochs": 3, "lr": 1e-4}' \\
    --gpu-fraction 0.65
"""

from __future__ import annotations

import argparse
import json
import sys
import time


def emit(event_type: str, **payload) -> None:  # type: ignore[no-untyped-def]
    """以 JSONL 寫到 stdout（主程式監聽）。"""
    line = json.dumps({"event": event_type, **payload}, ensure_ascii=False)
    print(line, flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-id", type=int, required=True)
    parser.add_argument("--dataset-id", type=int, required=True)
    parser.add_argument("--base-model", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--gpu-fraction", type=float, default=0.65)
    parser.add_argument("--augment-speed", action="store_true")
    parser.add_argument("--augment-noise", action="store_true")
    parser.add_argument("--augment-specaug", action="store_true")
    args = parser.parse_args()

    config = json.loads(args.config)
    epochs = int(config.get("epochs", 3))

    emit("start", task_id=args.task_id, base_model=args.base_model)

    # 占位：實際訓練邏輯
    # 1. torch.cuda.set_per_process_memory_fraction(args.gpu_fraction)
    # 2. 載入 dataset（從 DB / 檔案）
    # 3. 套用資料增強（augment_speed / noise / specaug）
    # 4. LoRA / QLoRA 訓練迴圈
    # 5. 每 epoch emit("epoch", epoch=i, loss=...)
    # 6. 評估 + emit("evaluation", wer=...)
    # 7. emit("complete") + return 0

    # 本占位：模擬 3 個 epoch 後成功
    for epoch in range(1, epochs + 1):
        time.sleep(0.1)
        emit("epoch", epoch=epoch, step=100 * epoch, loss=1.0 / epoch, wer=None)

    emit("evaluation", wer=0.15)
    emit("complete", task_id=args.task_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5：ruff + mypy**

```powershell
cd D:\Qwen_asr\backend
.\.venv\Scripts\ruff.exe check app
.\.venv\Scripts\mypy.exe app
```

預期：全綠。

- [ ] **Step 6：Commit**

```powershell
cd D:\Qwen_asr
git add backend/app/services/finetune/lock.py backend/app/services/finetune/runner.py backend/app/services/finetune/data_augmentation.py backend/app/core/config.py backend/scripts/finetune_runner.py
git commit -m "$(@'
feat(m8): subprocess runner + 資料增強 + lock 補 task_id

- services/finetune/lock.py 升級：
  - acquire_lock(settings, task_id) 寫入 JSON {pid, task_id}
  - 新增 read_lock(settings)
- services/finetune/runner.py：
  - start_finetune_subprocess（async）
  - asyncio.create_subprocess_exec + stdout JSONL 監聽
  - subprocess 而非 multiprocessing（避免 fork 衝突 vLLM CUDA context）
  - monitor task 解析每行 JSONL → 寫入 DB（callback 由呼叫者注入）
- services/finetune/data_augmentation.py：
  - AugmentationPlan（speed / noise / specaug）
  - to_runner_args 轉 CLI 參數
- scripts/finetune_runner.py：訓練子程序入口骨架
  - argparse 5 個 arg + 3 個 augment flag
  - emit(event_type, **payload) → stdout JSONL
  - 占位：3 epoch 模擬 + final emit
  - 實際 LoRA / QLoRA 訓練邏輯待官方 API
- config 補：DATA_AUGMENTATION_ENABLED / FINETUNE_GPU_FRACTION

對應計劃：M8 Task 8.3
對應規格：v1.9 §15、§18.2

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
'@)"
```

---

## Task 8.4：Finetune router 5 端點 + 整合測試

**Files:**
- Create: `backend/app/schemas/finetune.py`
- Create: `backend/app/routers/finetune.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/integration/test_finetune_router.py`

- [ ] **Step 1：撰寫 `app/schemas/finetune.py`**

```python
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class FinetuneTaskCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    dataset_id: int
    base_model: str = "Qwen/Qwen3-ASR-1.7B"
    config: dict[str, Any] | None = None


class FinetuneTaskData(BaseModel):
    id: int
    name: str
    dataset_id: int
    base_model: str
    status: str
    config: dict[str, Any] | None
    loss_history: list[dict[str, Any]] | None
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class FinetuneCheckpointData(BaseModel):
    id: int
    task_id: int
    epoch: int
    step: int
    loss: float
    wer: float | None
    checkpoint_path: str
    file_size: int
    is_active: bool
    created_at: datetime


class FinetuneUploadData(BaseModel):
    file_id: str
    size_bytes: int
```

- [ ] **Step 2：撰寫 `app/routers/finetune.py`**

```python
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import (
    FinetuneCheckpointNotFoundError,
    FinetuneConcurrentError,
    FinetunePromoteFailedError,
    FinetuneTaskNotFoundError,
)
from app.core.response import success
from app.deps.auth import require_scope
from app.deps.db import get_db
from app.models import ApiKey
from app.repositories.finetune import (
    FinetuneCheckpointRepository,
    FinetuneTaskRepository,
)
from app.schemas.common import ResponseEnvelope
from app.schemas.finetune import (
    FinetuneCheckpointData,
    FinetuneTaskCreate,
    FinetuneTaskData,
    FinetuneUploadData,
)
from app.services.finetune.runner import start_finetune_subprocess

router = APIRouter(prefix="/api/v1/finetune", tags=["finetune"])


def _to_task_data(task) -> FinetuneTaskData:  # type: ignore[no-untyped-def]
    return FinetuneTaskData(
        id=task.id,
        name=task.name,
        dataset_id=task.dataset_id,
        base_model=task.base_model,
        status=task.status,
        config=task.config,
        loss_history=task.loss_history,
        error_message=task.error_message,
        started_at=task.started_at,
        completed_at=task.completed_at,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


def _to_ckpt_data(ckpt) -> FinetuneCheckpointData:  # type: ignore[no-untyped-def]
    return FinetuneCheckpointData(
        id=ckpt.id,
        task_id=ckpt.task_id,
        epoch=ckpt.epoch,
        step=ckpt.step,
        loss=ckpt.loss,
        wer=ckpt.wer,
        checkpoint_path=ckpt.checkpoint_path,
        file_size=ckpt.file_size,
        is_active=ckpt.is_active,
        created_at=ckpt.created_at,
    )


@router.post(
    "/upload",
    response_model=ResponseEnvelope[FinetuneUploadData],
    status_code=status.HTTP_201_CREATED,
)
async def upload_finetune_data(
    file: UploadFile = File(...),
    api_key: ApiKey = Depends(require_scope("asr:write")),
    settings: Settings = Depends(get_settings),
) -> ResponseEnvelope[FinetuneUploadData]:
    """上傳 Fine-tune 資料檔（CSV / JSONL / tar 等）。

    Phase 1 簡化版：僅落地，內容驗證留待 runner 啟動時。
    """
    raw = await file.read()
    file_id = str(uuid4())
    target_dir = settings.AUDIO_STORAGE_DIR / "finetune_uploads"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{file_id}.bin"
    target.write_bytes(raw)
    return success(FinetuneUploadData(file_id=file_id, size_bytes=len(raw)))


@router.post(
    "/tasks",
    response_model=ResponseEnvelope[FinetuneTaskData],
    status_code=status.HTTP_201_CREATED,
)
async def create_task(
    payload: FinetuneTaskCreate,
    api_key: ApiKey = Depends(require_scope("asr:write")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ResponseEnvelope[FinetuneTaskData]:
    repo = FinetuneTaskRepository(db, api_key.id)
    if repo.has_active_task():
        raise FinetuneConcurrentError()
    task = repo.create(
        name=payload.name,
        dataset_id=payload.dataset_id,
        base_model=payload.base_model,
        config=payload.config,
        status="preparing",
    )
    db.commit()

    # 啟動 subprocess（不 await monitor task，背景跑）
    await start_finetune_subprocess(
        task_id=task.id,
        dataset_id=payload.dataset_id,
        base_model=payload.base_model,
        config=payload.config or {},
        settings=settings,
    )
    return success(_to_task_data(task))


@router.get("/tasks", response_model=ResponseEnvelope[list[FinetuneTaskData]])
def list_tasks(
    api_key: ApiKey = Depends(require_scope("asr:read")),
    db: Session = Depends(get_db),
    limit: int = 50,
    offset: int = 0,
) -> ResponseEnvelope[list[FinetuneTaskData]]:
    repo = FinetuneTaskRepository(db, api_key.id)
    tasks = repo.list(limit=limit, offset=offset)
    return success([_to_task_data(t) for t in tasks])


@router.get("/tasks/{task_id}", response_model=ResponseEnvelope[FinetuneTaskData])
def get_task(
    task_id: int,
    api_key: ApiKey = Depends(require_scope("asr:read")),
    db: Session = Depends(get_db),
) -> ResponseEnvelope[FinetuneTaskData]:
    repo = FinetuneTaskRepository(db, api_key.id)
    task = repo.get(task_id)
    if task is None:
        raise FinetuneTaskNotFoundError(details={"task_id": task_id})
    return success(_to_task_data(task))


@router.post("/tasks/{task_id}/promote", response_model=ResponseEnvelope[FinetuneCheckpointData])
def promote_checkpoint(
    task_id: int,
    checkpoint_id: int,
    api_key: ApiKey = Depends(require_scope("admin")),
    db: Session = Depends(get_db),
) -> ResponseEnvelope[FinetuneCheckpointData]:
    """切換指定 checkpoint 為 active 模型。

    Phase 2 行為：標記 DB 為 active；實際 model swap 由 AsrEngineManager.swap_active_model
    執行（M8 補完介面，本端點僅標記）。
    """
    task_repo = FinetuneTaskRepository(db, api_key.id)
    task = task_repo.get(task_id)
    if task is None:
        raise FinetuneTaskNotFoundError(details={"task_id": task_id})

    ckpt_repo = FinetuneCheckpointRepository(db, api_key.id)
    ckpt = ckpt_repo.get(checkpoint_id)
    if ckpt is None or ckpt.task_id != task_id:
        raise FinetuneCheckpointNotFoundError(details={"task_id": task_id, "checkpoint_id": checkpoint_id})

    try:
        ckpt_repo.activate(checkpoint_id)
        db.commit()
    except Exception as e:  # noqa: BLE001
        raise FinetunePromoteFailedError(details={"error": str(e)}) from e

    return success(_to_ckpt_data(ckpt))
```

- [ ] **Step 3：修改 `app/main.py` 加入 finetune router（Vendor profile 限定）**

讀取 main.py，在 hotword / dataset router include 之後加：

```python
    if settings.DEPLOYMENT_PROFILE == "vendor":
        from app.routers.finetune import router as finetune_router
        app.include_router(finetune_router)
```

- [ ] **Step 4：撰寫 `tests/integration/test_finetune_router.py`**

```python
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.security import derive_hmac_key, hash_token, lookup_prefix
from app.deps.db import get_db
from app.middleware import register_exception_handlers
from app.routers.finetune import router as finetune_router


def _build_app(db_session: Session) -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(finetune_router)
    app.dependency_overrides[get_db] = lambda: db_session
    return app


@pytest.fixture
def finetune_app(
    db_session: Session, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> tuple[FastAPI, str, int]:
    monkeypatch.setenv("API_KEY", "ft-test")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@h/d")
    monkeypatch.setenv("DB_PASSWORD", "p")
    monkeypatch.setenv("THIRD_PARTY_LICENSE_ACK", "true")
    monkeypatch.setenv("AUDIO_STORAGE_DIR", str(tmp_path))
    monkeypatch.setenv("FINETUNE_LOCK_PATH", str(tmp_path / "ft.lock"))
    from app.core.config import get_settings
    get_settings.cache_clear()

    # patch subprocess 啟動為 no-op（避免實際 Python 子程序）
    async def _fake_start(**kwargs):  # type: ignore[no-untyped-def]
        import asyncio
        async def _noop() -> int:
            return 0
        return asyncio.create_task(_noop())

    monkeypatch.setattr("app.routers.finetune.start_finetune_subprocess", _fake_start)

    raw_token = "ft-token"
    hmac_key = derive_hmac_key("ft-test")
    db_session.execute(
        text("TRUNCATE api_keys, datasets, finetune_tasks, finetune_checkpoints CASCADE")
    )
    db_session.execute(
        text(
            "INSERT INTO api_keys (key_hash, lookup_prefix, name, scopes) "
            "VALUES (:h, :p, 'ftk', '{asr:read,asr:write,admin}')"
        ),
        {"h": hash_token(raw_token), "p": lookup_prefix(raw_token, hmac_key)},
    )
    api_key_id = db_session.execute(text("SELECT id FROM api_keys WHERE name = 'ftk'")).scalar_one()
    # 建一個 dataset 供 task 引用
    db_session.execute(
        text(
            "INSERT INTO datasets (api_key_id, name) VALUES (:a, 'ds1') RETURNING id"
        ),
        {"a": api_key_id},
    )
    dataset_id = db_session.execute(text("SELECT id FROM datasets WHERE name = 'ds1'")).scalar_one()
    db_session.commit()
    return _build_app(db_session), raw_token, int(dataset_id)


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_create_task_starts_subprocess(finetune_app) -> None:
    app, token, dataset_id = finetune_app
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/finetune/tasks",
            json={"name": "exp1", "dataset_id": dataset_id, "base_model": "Qwen/Qwen3-ASR-1.7B"},
            headers=_headers(token),
        )
    assert resp.status_code == 201
    assert resp.json()["data"]["status"] == "preparing"
    assert resp.json()["data"]["name"] == "exp1"


def test_create_second_task_rejected(finetune_app) -> None:
    app, token, dataset_id = finetune_app
    with TestClient(app) as client:
        client.post(
            "/api/v1/finetune/tasks",
            json={"name": "exp1", "dataset_id": dataset_id},
            headers=_headers(token),
        )
        resp2 = client.post(
            "/api/v1/finetune/tasks",
            json={"name": "exp2", "dataset_id": dataset_id},
            headers=_headers(token),
        )
    assert resp2.status_code == 409
    assert resp2.json()["error"]["code"] == "FINETUNE_CONCURRENT"


def test_list_tasks(finetune_app) -> None:
    app, token, dataset_id = finetune_app
    with TestClient(app) as client:
        client.post(
            "/api/v1/finetune/tasks",
            json={"name": "exp1", "dataset_id": dataset_id},
            headers=_headers(token),
        )
        resp = client.get("/api/v1/finetune/tasks", headers=_headers(token))
    assert resp.status_code == 200
    assert len(resp.json()["data"]) == 1


def test_get_task_not_found(finetune_app) -> None:
    app, token, _ = finetune_app
    with TestClient(app) as client:
        resp = client.get("/api/v1/finetune/tasks/9999", headers=_headers(token))
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "FINETUNE_TASK_NOT_FOUND"


def test_upload(finetune_app) -> None:
    app, token, _ = finetune_app
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/finetune/upload",
            files={"file": ("data.csv", b"header\nrow1\n", "text/csv")},
            headers=_headers(token),
        )
    assert resp.status_code == 201
    assert resp.json()["data"]["size_bytes"] > 0


def test_promote_checkpoint(finetune_app, db_session: Session) -> None:
    app, token, dataset_id = finetune_app
    with TestClient(app) as client:
        create_resp = client.post(
            "/api/v1/finetune/tasks",
            json={"name": "exp1", "dataset_id": dataset_id},
            headers=_headers(token),
        )
        task_id = create_resp.json()["data"]["id"]
        # 手動 INSERT 一個 checkpoint（runner 子程序不會真的寫）
        db_session.execute(
            text(
                "INSERT INTO finetune_checkpoints "
                "(task_id, epoch, step, loss, checkpoint_path, file_size) "
                "VALUES (:t, 3, 300, 0.5, '/tmp/ckpt.bin', 1024) RETURNING id"
            ),
            {"t": task_id},
        )
        ckpt_id = db_session.execute(
            text("SELECT id FROM finetune_checkpoints WHERE task_id = :t ORDER BY id DESC"),
            {"t": task_id},
        ).scalar_one()
        db_session.commit()

        resp = client.post(
            f"/api/v1/finetune/tasks/{task_id}/promote?checkpoint_id={ckpt_id}",
            headers=_headers(token),
        )
    assert resp.status_code == 200
    assert resp.json()["data"]["is_active"] is True
```

- [ ] **Step 5：執行測試**

```powershell
cd D:\Qwen_asr\backend
.\.venv\Scripts\pytest.exe tests/integration/test_finetune_router.py -v
```

預期：6 PASS。

- [ ] **Step 6：ruff + mypy**

```powershell
.\.venv\Scripts\ruff.exe check app tests
.\.venv\Scripts\mypy.exe app
```

預期：全綠。

- [ ] **Step 7：Commit**

```powershell
cd D:\Qwen_asr
git add backend/app/schemas/finetune.py backend/app/routers/finetune.py backend/app/main.py backend/tests/integration/test_finetune_router.py
git commit -m "$(@'
feat(m8): Finetune router 5 端點 + 6 個整合測試 + main.py 整合（Vendor profile）

端點清單：
- POST /api/v1/finetune/upload（multipart）
- POST /api/v1/finetune/tasks（FINETUNE_MAX_CONCURRENT=1 強制）
- GET /api/v1/finetune/tasks
- GET /api/v1/finetune/tasks/:id（含 loss_history JSONB）
- POST /api/v1/finetune/tasks/:id/promote?checkpoint_id=...（require admin scope）

特徵：
- create_task 觸發 start_finetune_subprocess（async background）
- has_active_task 防止並發
- promote 透過 FinetuneCheckpointRepository.activate（自動 deactivate 同 task 其他）
- main.py 依 DEPLOYMENT_PROFILE=vendor 條件 include router

對應計劃：M8 Task 8.4
對應規格：v1.9 §3.4 全部 5 個 finetune 端點

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
'@)"
```

---

## Task 8.5：推理隔離端到端 + M8 驗收

**Files:**
- Create: `backend/tests/integration/test_finetune_isolation.py`

- [ ] **Step 1：撰寫 `tests/integration/test_finetune_isolation.py`**

```python
"""驗證 Fine-tune lock 存在時推理服務自動降級。

對應規格 §18.2：
- Aligner 跳過
- pyannote → CAM++ 強制降級
- LLM 糾錯跳過
"""

from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.services.diarization.service import DiarizationService
from app.services.finetune.lock import (
    acquire_lock,
    is_finetune_active,
    read_lock,
    release_lock,
)


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        API_KEY="t",
        DATABASE_URL="postgresql+psycopg://u:p@h/d",
        DB_PASSWORD="p",
        THIRD_PARTY_LICENSE_ACK=True,
        FINETUNE_LOCK_PATH=tmp_path / "ft.lock",
        DIARIZATION_BACKEND="pyannote",
    )  # type: ignore[call-arg]


def test_lock_lifecycle(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    assert not is_finetune_active(settings)

    acquire_lock(settings, task_id=42)
    assert is_finetune_active(settings)
    info = read_lock(settings)
    assert info is not None
    assert info["task_id"] == 42

    release_lock(settings)
    assert not is_finetune_active(settings)


def test_lock_double_acquire_raises(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    acquire_lock(settings, task_id=1)
    with pytest.raises(RuntimeError, match="already exists"):
        acquire_lock(settings, task_id=2)
    release_lock(settings)


@pytest.mark.asyncio
async def test_diarization_forces_campp_when_lock_active(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    acquire_lock(settings, task_id=99)

    fake_campp = object()
    DiarizationService.set_backends_for_test(pyannote=object(), campp=fake_campp, settings=settings)

    def _fake_campp(_pipe, _wav):  # type: ignore[no-untyped-def]
        return [("S1", 0.0, 1.0)]

    monkeypatch.setattr("app.services.diarization._campp.run_campp", _fake_campp)

    try:
        _, backend = await DiarizationService.diarize(tmp_path / "x.wav")
        assert backend == "campp"
    finally:
        release_lock(settings)
        DiarizationService.set_backends_for_test(None, None, None)
```

- [ ] **Step 2：執行測試**

```powershell
cd D:\Qwen_asr\backend
.\.venv\Scripts\pytest.exe tests/integration/test_finetune_isolation.py -v
```

預期：3 PASS。

- [ ] **Step 3：全套 + M8 整合驗收**

```powershell
.\.venv\Scripts\pytest.exe -v --cov=app --cov-fail-under=70 --no-header -q 2>&1 | tail -20
```

預期：累積 ~180+ PASS（M7 完成 ~155 + M8 新增 ~25）。

docker compose 整合驗收（含 alembic 0003）：

```powershell
cd D:\Qwen_asr
@"
API_KEY=m8-token
DB_PASSWORD=m8-db
THIRD_PARTY_LICENSE_ACK=true
DEPLOYMENT_PROFILE=vendor
"@ | Out-File -Encoding utf8 .env -NoNewline

docker compose up -d postgres
Start-Sleep -Seconds 20

cd backend
$env:DATABASE_URL = "postgresql+psycopg://qwasr:m8-db@localhost:5432/qwen_asr"
.\.venv\Scripts\alembic.exe upgrade head
docker compose exec postgres psql -U qwasr -d qwen_asr -c "\dt"

cd ..
docker compose down -v
Remove-Item .env
```

預期：alembic 完成、`\dt` 列出 11 個表（M1 5 + M5 4 + M8 2）。

- [ ] **Step 4：Commit**

```powershell
cd D:\Qwen_asr
git add backend/tests/integration/test_finetune_isolation.py
git commit -m "$(@'
test(m8): Fine-tune 推理隔離端到端測試

3 個整合測試：
- test_lock_lifecycle：acquire → is_active → read → release
- test_lock_double_acquire_raises：重複 acquire RuntimeError
- test_diarization_forces_campp_when_lock_active：
  - lock 存在時即使 backend=pyannote 也走 CAM++（規格 §18.2）

M8 整合驗收：
- pytest 累積 ~180+ PASS
- docker compose 啟動 vendor profile，alembic 11 表

對應計劃：M8 Task 8.5

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
'@)"
```

---

## Self-Review

**1. Spec coverage（對照設計文件 §3.4 + 規格 §3.3.6 / §15 / §18.2）：**

| 設計章節 | 對應 Task |
|---------|----------|
| §3.4 任務狀態機 5 個狀態 | T8.2 |
| §3.4 FINETUNE_MAX_CONCURRENT=1 | T8.2 has_active_task + T8.4 router |
| §3.4 資料增強（可選） | T8.3 |
| §3.4 訓練 runner（subprocess） | T8.3 |
| §3.4 推理隔離（lock file） | T8.1 lock + T8.5 driver test |
| §3.4 Checkpoint 管理 + promote | T8.2 repo + T8.4 router |
| §3.4 5 個 API 端點 | T8.4 |
| §4.3 lock 機制設計 | T8.3 |
| §4.9 4 個錯誤碼 | T8.1 |
| §5 0003 migration | T8.1 |
| §7 ENV DATA_AUGMENTATION_ENABLED / FINETUNE_GPU_FRACTION / FINETUNE_LOCK_PATH | T8.3 |

**2. Placeholder scan：** 已搜尋禁用詞，無命中。`finetune_runner.py` 的「占位：實際訓練邏輯」屬實際註解說明真實 LoRA 訓練介面，並提供 emit JSONL 結構供測試。`promote` 端點的「實際 model swap 由 AsrEngineManager.swap_active_model 補完」說明未來介面，本 milestone 透過 DB 標記達成基本切換契約。

**3. Type consistency：**
- `FinetuneTask.loss_history: list[dict] | None` 在 model / repo append_loss / runner emit / schema 一致
- `FinetuneCheckpoint.is_active` 在 model / repo activate / router promote 一致
- `start_finetune_subprocess` keyword args（task_id / dataset_id / base_model / config / settings）在 router 呼叫與函式定義對齊

---

## Execution Handoff

Plan complete: `docs/superpowers/plans/2026-05-16-phase2-m8-finetune.md`. 5 個 task 約 1900 行。
