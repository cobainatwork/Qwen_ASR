# Phase 2 / M5 — REST API 端點（Hotword + Dataset）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 M2-M4 後端骨架上實作 Hotword 三層架構（< 100 Shallow Fusion / 100-1000 CTC-WS / > 1000 拒絕導向 Fine-tune）與 Dataset CRUD（10 個 API 端點），完成後 Hotword 規模分流可運作、Dataset 樣本可入庫。

**Architecture:** 沿用 M2 既有 `TenantScopedRepository[T]` / `ResponseEnvelope` / `AppException` / `require_scope`。Hotword 服務透過 `HotwordDispatcher.select_strategy(group_id)` 依詞數決定 `ShallowFusionStrategy` / `CtcWsStrategy` 或拋 `HotwordTooLargeError`。Dataset 樣本透過 M3 既有 `verify_mime` + `store_upload` + `resample_to_16k_mono` pipeline 入庫，**僅儲存路徑與 metadata，實際內容用於 M8 Fine-tune**。

**Tech Stack:** M1-M4 既有（FastAPI 0.115、SQLAlchemy 2.0、Alembic 1.14、pytest）。無新增第三方依賴。

**對應設計文件：** `docs/superpowers/specs/2026-05-16-phase2-implementation-design.md` §3.1、§4.5、§5、§6。

---

## File Structure

| 路徑 | 動作 | 責任 |
|------|------|------|
| `backend/app/models/hotword.py` | Create | `HotwordGroup` / `Hotword` ORM |
| `backend/app/models/dataset.py` | Create | `Dataset` / `DatasetSample` ORM |
| `backend/app/models/__init__.py` | Modify | 補 re-export |
| `backend/app/schemas/hotword.py` | Create | Pydantic schema（含 `HotwordGroupData` / `HotwordCreate` / `BulkUploadData`） |
| `backend/app/schemas/dataset.py` | Create | Pydantic schema |
| `backend/app/repositories/hotword.py` | Create | `HotwordGroupRepository` + `HotwordRepository` |
| `backend/app/repositories/dataset.py` | Create | `DatasetRepository` + `DatasetSampleRepository` |
| `backend/app/services/hotword/__init__.py` | Create | re-export `HotwordDispatcher` |
| `backend/app/services/hotword/dispatcher.py` | Create | `select_strategy(group_id, db)` 三層分流 |
| `backend/app/services/hotword/strategies.py` | Create | `HotwordStrategy` ABC + 兩個實作 |
| `backend/app/services/dataset/__init__.py` | Create | re-export `process_sample` |
| `backend/app/services/dataset/sample_processor.py` | Create | 樣本處理流程（MIME + store + resample） |
| `backend/app/routers/hotword.py` | Create | 6 個 Hotword 端點 |
| `backend/app/routers/dataset.py` | Create | 4 個 Dataset 端點 |
| `backend/app/core/exceptions.py` | Modify | 新增 4 個錯誤碼類別 |
| `backend/alembic/versions/0002_hotword_dataset.py` | Create | DB schema 變更 |
| `backend/app/main.py` | Modify | include hotword / dataset router |
| `backend/tests/unit/test_hotword_dispatcher.py` | Create | dispatcher 單元測試 |
| `backend/tests/integration/test_hotword_router.py` | Create | 6 個端點整合測試 |
| `backend/tests/integration/test_dataset_router.py` | Create | 4 個端點整合測試 |

---

## Task 5.1：ORM models 與 migration（Hotword + Dataset）

**Files:**
- Create: `backend/app/models/hotword.py`
- Create: `backend/app/models/dataset.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/0002_hotword_dataset.py`

- [ ] **Step 1：撰寫 `app/models/hotword.py`**

```python
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin


class HotwordGroup(Base, TenantMixin):
    __tablename__ = "hotword_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    word_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class Hotword(Base):
    __tablename__ = "hotwords"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("hotword_groups.id", ondelete="CASCADE"), nullable=False, index=True
    )
    word: Mapped[str] = mapped_column(String(100), nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False, server_default="1.0")
    pinyin: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
```

- [ ] **Step 2：撰寫 `app/models/dataset.py`**

```python
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin


class Dataset(Base, TenantMixin):
    __tablename__ = "datasets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    total_duration_sec: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    metadata_: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSONB, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class DatasetSample(Base):
    __tablename__ = "dataset_samples"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dataset_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    audio_file_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("audio_files.id"), nullable=False
    )
    transcript: Mapped[str] = mapped_column(Text, nullable=False)
    duration_sec: Mapped[float] = mapped_column(Float, nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
```

- [ ] **Step 3：修改 `app/models/__init__.py` 補 re-export**

讀取既有檔案後在 import 區補加：

```python
from app.models.dataset import Dataset, DatasetSample
from app.models.hotword import Hotword, HotwordGroup
```

`__all__` 補：`"Dataset", "DatasetSample", "Hotword", "HotwordGroup"`

- [ ] **Step 4：撰寫 `backend/alembic/versions/0002_hotword_dataset.py`**

```python
"""Phase 2 / M5：hotword_groups / hotwords / datasets / dataset_samples

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-16

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # hotword_groups
    op.create_table(
        "hotword_groups",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("api_key_id", sa.Integer(), sa.ForeignKey("api_keys.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("word_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_hotword_groups_api_key_id", "hotword_groups", ["api_key_id"])

    # hotwords
    op.create_table(
        "hotwords",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("group_id", sa.Integer(), sa.ForeignKey("hotword_groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("word", sa.String(100), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("pinyin", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_hotwords_group_id", "hotwords", ["group_id"])

    # datasets
    op.create_table(
        "datasets",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("api_key_id", sa.Integer(), sa.ForeignKey("api_keys.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sample_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_duration_sec", sa.Float(), nullable=False, server_default="0"),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_datasets_api_key_id", "datasets", ["api_key_id"])

    # dataset_samples
    op.create_table(
        "dataset_samples",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("dataset_id", sa.Integer(), sa.ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("audio_file_id", sa.Integer(), sa.ForeignKey("audio_files.id"), nullable=False),
        sa.Column("transcript", sa.Text(), nullable=False),
        sa.Column("duration_sec", sa.Float(), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_dataset_samples_dataset_id", "dataset_samples", ["dataset_id"])

    # updated_at trigger（複用 0001 既有 set_updated_at function）
    op.execute("CREATE TRIGGER trg_hotword_groups_updated_at BEFORE UPDATE ON hotword_groups FOR EACH ROW EXECUTE FUNCTION set_updated_at();")
    op.execute("CREATE TRIGGER trg_datasets_updated_at BEFORE UPDATE ON datasets FOR EACH ROW EXECUTE FUNCTION set_updated_at();")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_datasets_updated_at ON datasets")
    op.execute("DROP TRIGGER IF EXISTS trg_hotword_groups_updated_at ON hotword_groups")
    op.drop_table("dataset_samples")
    op.drop_table("datasets")
    op.drop_table("hotwords")
    op.drop_table("hotword_groups")
```

- [ ] **Step 5：執行 alembic 驗證 round-trip**

```powershell
cd D:\Qwen_asr
docker compose up -d postgres
Start-Sleep -Seconds 20

cd backend
$env:DATABASE_URL = "postgresql+psycopg://qwasr:devpass@localhost:5432/qwen_asr"
.\.venv\Scripts\alembic.exe upgrade head
docker compose exec postgres psql -U qwasr -d qwen_asr -c "\dt"
.\.venv\Scripts\alembic.exe downgrade 0001
docker compose exec postgres psql -U qwasr -d qwen_asr -c "\dt"
.\.venv\Scripts\alembic.exe upgrade head
cd ..
docker compose down -v
```

預期：`\dt` 第一次列出 9 個表（M1 5 + 0002 新增 4），downgrade 後回到 5 個，再次 upgrade 回到 9 個。

- [ ] **Step 6：ruff + mypy**

```powershell
cd D:\Qwen_asr\backend
.\.venv\Scripts\ruff.exe check app
.\.venv\Scripts\mypy.exe app
```

預期：全綠。

- [ ] **Step 7：Commit**

```powershell
cd D:\Qwen_asr
git add backend/app/models/hotword.py backend/app/models/dataset.py backend/app/models/__init__.py backend/alembic/versions/0002_hotword_dataset.py
git commit -m "$(@'
feat(m5): 加入 Hotword / Dataset ORM models 與 0002 migration

- models/hotword.py：HotwordGroup（含 word_count 快取）+ Hotword（group_id FK CASCADE）
- models/dataset.py：Dataset（含 metadata JSONB / 統計欄位） + DatasetSample（FK audio_files）
- 4 個新表沿用 TenantMixin（api_key_id 自動掛載）
- updated_at trigger 複用 0001 既有 set_updated_at function
- alembic upgrade / downgrade / upgrade round-trip 驗證 PASS

對應計劃：docs/superpowers/plans/2026-05-16-phase2-m5-hotword-dataset.md Task 5.1
對應設計：docs/superpowers/specs/2026-05-16-phase2-implementation-design.md §3.1、§5

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
'@)"
```

---

## Task 5.2：擴充 exceptions（4 個錯誤碼）

**Files:**
- Modify: `backend/app/core/exceptions.py`
- Modify: `backend/tests/unit/test_exceptions.py`（補測試）

- [ ] **Step 1：讀取既有 `app/core/exceptions.py`，在 ALL_ERROR_CODES 前加入 4 個類別**

在 `class QueueFullError` 之後加入：

```python
# ----- Phase 2 / M5 -----
class HotwordGroupNotFoundError(AppException):
    code = "HOTWORD_GROUP_NOT_FOUND"
    http_status = 404
    message = "Hotword 群組不存在"


class HotwordTooLargeError(AppException):
    code = "HOTWORD_TOO_LARGE"
    http_status = 422
    message = "Hotword 群組超過 1000 詞，請建立 Fine-tune 任務"


class DatasetNotFoundError(AppException):
    code = "DATASET_NOT_FOUND"
    http_status = 404
    message = "Dataset 不存在"


class DatasetSampleInvalidError(AppException):
    code = "DATASET_SAMPLE_INVALID"
    http_status = 400
    message = "樣本資料不符規範"
```

- [ ] **Step 2：擴充 `ALL_ERROR_CODES` tuple**

在 tuple 末尾（`"QUEUE_FULL",` 之後）加入：

```python
    "HOTWORD_GROUP_NOT_FOUND",
    "HOTWORD_TOO_LARGE",
    "DATASET_NOT_FOUND",
    "DATASET_SAMPLE_INVALID",
```

- [ ] **Step 3：修改 `tests/unit/test_exceptions.py` 補測試**

在既有檔案末尾追加：

```python
from app.core.exceptions import (
    DatasetNotFoundError,
    DatasetSampleInvalidError,
    HotwordGroupNotFoundError,
    HotwordTooLargeError,
)


def test_m5_error_codes_defaults() -> None:
    assert HotwordGroupNotFoundError().code == "HOTWORD_GROUP_NOT_FOUND"
    assert HotwordGroupNotFoundError().http_status == 404
    assert HotwordTooLargeError().http_status == 422
    assert DatasetNotFoundError().http_status == 404
    assert DatasetSampleInvalidError().http_status == 400


def test_all_error_codes_includes_m5() -> None:
    assert "HOTWORD_GROUP_NOT_FOUND" in ALL_ERROR_CODES
    assert "HOTWORD_TOO_LARGE" in ALL_ERROR_CODES
    assert "DATASET_NOT_FOUND" in ALL_ERROR_CODES
    assert "DATASET_SAMPLE_INVALID" in ALL_ERROR_CODES
```

注意 import 需合併到既有 `from app.core.exceptions import (...)` 內，避免重複 import 觸發 ruff F811。

- [ ] **Step 4：執行測試**

```powershell
cd D:\Qwen_asr\backend
.\.venv\Scripts\pytest.exe tests/unit/test_exceptions.py -v
```

預期：既有測試 + 2 個新測試全 PASS。

- [ ] **Step 5：ruff + mypy**

```powershell
.\.venv\Scripts\ruff.exe check app tests
.\.venv\Scripts\mypy.exe app
```

預期：全綠。

- [ ] **Step 6：Commit**

```powershell
cd D:\Qwen_asr
git add backend/app/core/exceptions.py backend/tests/unit/test_exceptions.py
git commit -m "$(@'
feat(m5): exceptions 擴充 4 個 M5 錯誤碼

- HotwordGroupNotFoundError → HOTWORD_GROUP_NOT_FOUND / 404
- HotwordTooLargeError → HOTWORD_TOO_LARGE / 422（超過 1000 詞需 Fine-tune）
- DatasetNotFoundError → DATASET_NOT_FOUND / 404
- DatasetSampleInvalidError → DATASET_SAMPLE_INVALID / 400
- ALL_ERROR_CODES tuple 從 20 擴充到 24
- 2 個新單元測試（defaults + ALL_ERROR_CODES 覆蓋）

對應計劃：M5 Task 5.2
對應設計：Phase 2 design §4.9

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
'@)"
```

---

## Task 5.3：Repositories（Hotword + Dataset）

**Files:**
- Create: `backend/app/repositories/hotword.py`
- Create: `backend/app/repositories/dataset.py`

- [ ] **Step 1：撰寫 `app/repositories/hotword.py`**

```python
from sqlalchemy import func, select

from app.models import Hotword, HotwordGroup
from app.repositories.base import TenantScopedRepository


class HotwordGroupRepository(TenantScopedRepository[HotwordGroup]):
    model = HotwordGroup

    def count_words(self, group_id: int) -> int:
        result = self.db.execute(
            select(func.count(Hotword.id)).where(Hotword.group_id == group_id)
        ).scalar_one()
        return int(result)

    def refresh_word_count(self, group_id: int) -> None:
        group = self.get(group_id)
        if group is None:
            return
        group.word_count = self.count_words(group_id)
        self.db.flush()


class HotwordRepository:
    """Hotword（單字）跨群組存取，不繼承 TenantScopedRepository。

    Tenant 隔離透過 group_id → HotwordGroup.api_key_id 驗證實現。
    """

    def __init__(self, db, api_key_id: int) -> None:  # type: ignore[no-untyped-def]
        self.db = db
        self.api_key_id = api_key_id

    def list_by_group(self, group_id: int) -> list[Hotword]:
        return list(self.db.execute(
            select(Hotword).where(Hotword.group_id == group_id)
        ).scalars().all())

    def bulk_insert(self, group_id: int, words: list[dict]) -> int:
        """批次新增 hotword，回傳新增筆數。

        words 格式：[{"word": "...", "weight": 1.0, "pinyin": "..."}]
        """
        for w in words:
            self.db.add(Hotword(
                group_id=group_id,
                word=w["word"],
                weight=w.get("weight", 1.0),
                pinyin=w.get("pinyin"),
            ))
        self.db.flush()
        return len(words)
```

- [ ] **Step 2：撰寫 `app/repositories/dataset.py`**

```python
from sqlalchemy import func, select

from app.models import Dataset, DatasetSample
from app.repositories.base import TenantScopedRepository


class DatasetRepository(TenantScopedRepository[Dataset]):
    model = Dataset

    def refresh_stats(self, dataset_id: int) -> None:
        dataset = self.get(dataset_id)
        if dataset is None:
            return
        count_result = self.db.execute(
            select(func.count(DatasetSample.id)).where(DatasetSample.dataset_id == dataset_id)
        ).scalar_one()
        duration_result = self.db.execute(
            select(func.coalesce(func.sum(DatasetSample.duration_sec), 0.0)).where(
                DatasetSample.dataset_id == dataset_id
            )
        ).scalar_one()
        dataset.sample_count = int(count_result)
        dataset.total_duration_sec = float(duration_result)
        self.db.flush()


class DatasetSampleRepository:
    """Dataset 樣本跨 dataset 存取。

    Tenant 隔離透過 dataset_id → Dataset.api_key_id 驗證。
    """

    def __init__(self, db, api_key_id: int) -> None:  # type: ignore[no-untyped-def]
        self.db = db
        self.api_key_id = api_key_id

    def list_by_dataset(self, dataset_id: int, limit: int = 50, offset: int = 0) -> list[DatasetSample]:
        return list(self.db.execute(
            select(DatasetSample)
            .where(DatasetSample.dataset_id == dataset_id)
            .limit(limit)
            .offset(offset)
        ).scalars().all())

    def create(
        self,
        *,
        dataset_id: int,
        audio_file_id: int,
        transcript: str,
        duration_sec: float,
        file_size: int,
    ) -> DatasetSample:
        sample = DatasetSample(
            dataset_id=dataset_id,
            audio_file_id=audio_file_id,
            transcript=transcript,
            duration_sec=duration_sec,
            file_size=file_size,
        )
        self.db.add(sample)
        self.db.flush()
        return sample
```

- [ ] **Step 3：ruff + mypy**

```powershell
cd D:\Qwen_asr\backend
.\.venv\Scripts\ruff.exe check app
.\.venv\Scripts\mypy.exe app
```

預期：全綠。

- [ ] **Step 4：Commit**

```powershell
cd D:\Qwen_asr
git add backend/app/repositories/hotword.py backend/app/repositories/dataset.py
git commit -m "$(@'
feat(m5): 加入 HotwordGroupRepository / DatasetRepository 與單字、樣本子 repo

- HotwordGroupRepository（繼承 TenantScopedRepository[HotwordGroup]）
  - count_words：依 group_id 統計詞數（dispatcher 使用）
  - refresh_word_count：更新 HotwordGroup.word_count 快取欄位
- HotwordRepository（跨群組，不繼承 Tenant）
  - list_by_group / bulk_insert（批次新增詞彙）
  - Tenant 隔離透過 group_id → HotwordGroup.api_key_id 驗證（在 router 層）
- DatasetRepository（繼承 TenantScopedRepository[Dataset]）
  - refresh_stats：更新 sample_count / total_duration_sec 快取
- DatasetSampleRepository（跨 dataset，不繼承 Tenant）
  - list_by_dataset（含 pagination）/ create

對應計劃：M5 Task 5.3

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
'@)"
```

---

## Task 5.4：Hotword Dispatcher + Strategies

**Files:**
- Create: `backend/app/services/hotword/__init__.py`
- Create: `backend/app/services/hotword/strategies.py`
- Create: `backend/app/services/hotword/dispatcher.py`
- Create: `backend/tests/unit/test_hotword_dispatcher.py`

- [ ] **Step 1：建立目錄**

```powershell
cd D:\Qwen_asr\backend
New-Item app/services/hotword -ItemType Directory -Force
```

- [ ] **Step 2：撰寫 `app/services/hotword/strategies.py`**

```python
"""Hotword 推理整合策略（規格 §13.2）。

三層架構：
- ShallowFusionStrategy：< 100 詞，推理時 logits 加權
- CtcWsStrategy：100-1000 詞，CTC Word Spotter
- > 1000 詞：dispatcher 層拋 HotwordTooLargeError，導向 Fine-tune
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class HotwordContext:
    """傳遞給 ASR 推理引擎的 Hotword context。

    M4 既有 Transcriber.run 未使用此 context；Phase 2 後續 milestone
    （或單獨 PR）將整合至 ASR pipeline。
    """

    group_id: int
    strategy_name: str
    words: list[str]
    weights: list[float]


class HotwordStrategy(ABC):
    """所有策略的共同介面。"""

    @abstractmethod
    def build_context(self, group_id: int, words: list[dict]) -> HotwordContext: ...

    @property
    @abstractmethod
    def name(self) -> str: ...


class ShallowFusionStrategy(HotwordStrategy):
    @property
    def name(self) -> str:
        return "shallow_fusion"

    def build_context(self, group_id: int, words: list[dict]) -> HotwordContext:
        return HotwordContext(
            group_id=group_id,
            strategy_name=self.name,
            words=[w["word"] for w in words],
            weights=[w.get("weight", 1.0) for w in words],
        )


class CtcWsStrategy(HotwordStrategy):
    @property
    def name(self) -> str:
        return "ctc_ws"

    def build_context(self, group_id: int, words: list[dict]) -> HotwordContext:
        return HotwordContext(
            group_id=group_id,
            strategy_name=self.name,
            words=[w["word"] for w in words],
            weights=[w.get("weight", 1.0) for w in words],
        )
```

- [ ] **Step 3：撰寫 `app/services/hotword/dispatcher.py`**

```python
"""Hotword 三層分流決策器（規格 §13.4）。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import HotwordTooLargeError
from app.repositories.hotword import HotwordGroupRepository
from app.services.hotword.strategies import (
    CtcWsStrategy,
    HotwordStrategy,
    ShallowFusionStrategy,
)


def select_strategy(
    group_id: int,
    db: Session,
    api_key_id: int,
    settings: Settings | None = None,
) -> HotwordStrategy:
    """依群組詞數選擇策略。

    閾值可由 ENV 覆寫（HOTWORD_SHALLOW_FUSION_THRESHOLD / HOTWORD_CTC_WS_THRESHOLD）。

    Raises:
        HotwordTooLargeError: 詞數 ≥ CTC_WS_THRESHOLD，需走 Fine-tune。
    """
    s = settings or get_settings()
    word_count = HotwordGroupRepository(db, api_key_id).count_words(group_id)

    if word_count < s.HOTWORD_SHALLOW_FUSION_THRESHOLD:
        return ShallowFusionStrategy()
    if word_count < s.HOTWORD_CTC_WS_THRESHOLD:
        return CtcWsStrategy()
    raise HotwordTooLargeError(
        message=f"Hotword 群組 {group_id} 含 {word_count} 詞，超過 CTC-WS 上限",
        details={
            "group_id": group_id,
            "word_count": word_count,
            "limit": s.HOTWORD_CTC_WS_THRESHOLD,
            "suggested_endpoint": "/api/v1/finetune/tasks",
        },
    )
```

- [ ] **Step 4：撰寫 `app/services/hotword/__init__.py`**

```python
from app.services.hotword.dispatcher import select_strategy
from app.services.hotword.strategies import (
    CtcWsStrategy,
    HotwordContext,
    HotwordStrategy,
    ShallowFusionStrategy,
)

__all__ = [
    "CtcWsStrategy",
    "HotwordContext",
    "HotwordStrategy",
    "ShallowFusionStrategy",
    "select_strategy",
]
```

- [ ] **Step 5：補 Settings 兩個 ENV**

修改 `backend/app/core/config.py`，在 `# ----- 補充：認證查找用 HMAC 密鑰 -----` 之前加入：

```python
    # ----- Hotword 三層分流閾值 -----
    HOTWORD_SHALLOW_FUSION_THRESHOLD: int = 100
    HOTWORD_CTC_WS_THRESHOLD: int = 1000
```

- [ ] **Step 6：撰寫 `tests/unit/test_hotword_dispatcher.py`**

```python
import pytest
from sqlalchemy.orm import Session

from app.core.exceptions import HotwordTooLargeError
from app.models import Hotword, HotwordGroup
from app.services.hotword.dispatcher import select_strategy
from app.services.hotword.strategies import CtcWsStrategy, ShallowFusionStrategy


def _seed_group(db: Session, api_key_id: int, word_count: int) -> int:
    group = HotwordGroup(api_key_id=api_key_id, name="test")
    db.add(group)
    db.flush()
    for i in range(word_count):
        db.add(Hotword(group_id=group.id, word=f"word{i}"))
    db.flush()
    return group.id


def test_under_100_returns_shallow_fusion(db_session: Session, seed_api_key: int) -> None:
    group_id = _seed_group(db_session, seed_api_key, word_count=50)
    strategy = select_strategy(group_id, db_session, seed_api_key)
    assert isinstance(strategy, ShallowFusionStrategy)


def test_between_100_and_1000_returns_ctc_ws(db_session: Session, seed_api_key: int) -> None:
    group_id = _seed_group(db_session, seed_api_key, word_count=500)
    strategy = select_strategy(group_id, db_session, seed_api_key)
    assert isinstance(strategy, CtcWsStrategy)


def test_at_or_above_1000_raises_too_large(db_session: Session, seed_api_key: int) -> None:
    group_id = _seed_group(db_session, seed_api_key, word_count=1000)
    with pytest.raises(HotwordTooLargeError) as exc:
        select_strategy(group_id, db_session, seed_api_key)
    assert exc.value.details["word_count"] == 1000
    assert exc.value.details["suggested_endpoint"] == "/api/v1/finetune/tasks"


def test_empty_group_returns_shallow_fusion(db_session: Session, seed_api_key: int) -> None:
    group_id = _seed_group(db_session, seed_api_key, word_count=0)
    strategy = select_strategy(group_id, db_session, seed_api_key)
    assert isinstance(strategy, ShallowFusionStrategy)
```

- [ ] **Step 7：執行測試**

```powershell
cd D:\Qwen_asr\backend
.\.venv\Scripts\pytest.exe tests/unit/test_hotword_dispatcher.py -v
```

預期：4 個測試 PASS。

- [ ] **Step 8：ruff + mypy**

```powershell
.\.venv\Scripts\ruff.exe check app tests
.\.venv\Scripts\mypy.exe app
```

預期：全綠。

- [ ] **Step 9：Commit**

```powershell
cd D:\Qwen_asr
git add backend/app/services/hotword backend/app/core/config.py backend/tests/unit/test_hotword_dispatcher.py
git commit -m "$(@'
feat(m5): 加入 Hotword 三層分流 dispatcher 與策略基底

- services/hotword/strategies.py：
  - HotwordStrategy ABC + HotwordContext dataclass
  - ShallowFusionStrategy（< 100 詞）
  - CtcWsStrategy（100-1000 詞）
- services/hotword/dispatcher.py：
  - select_strategy(group_id, db, api_key_id, settings)
  - 三層分流邏輯，> 1000 詞拋 HotwordTooLargeError 含 suggested_endpoint
- core/config.py 補 ENV：
  - HOTWORD_SHALLOW_FUSION_THRESHOLD（預設 100）
  - HOTWORD_CTC_WS_THRESHOLD（預設 1000）
- 4 個單元測試：< 100 / 100-1000 / ≥ 1000 / 空群組

對應計劃：M5 Task 5.4
對應設計：Phase 2 design §4.5（Hotword 三層架構切換邏輯）
對應規格：v1.9 §13.2 / §13.4

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
'@)"
```

---

## Task 5.5：Hotword schemas + router（6 端點）

**Files:**
- Create: `backend/app/schemas/hotword.py`
- Create: `backend/app/routers/hotword.py`

- [ ] **Step 1：撰寫 `app/schemas/hotword.py`**

```python
from datetime import datetime

from pydantic import BaseModel, Field


class HotwordGroupCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None


class HotwordGroupUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    is_active: bool | None = None


class HotwordGroupData(BaseModel):
    id: int
    name: str
    description: str | None
    is_active: bool
    word_count: int
    created_at: datetime
    updated_at: datetime


class HotwordItem(BaseModel):
    word: str = Field(..., min_length=1, max_length=100)
    weight: float = 1.0
    pinyin: str | None = None


class HotwordBulkUploadRequest(BaseModel):
    words: list[HotwordItem] = Field(..., min_length=1, max_length=2000)


class HotwordBulkUploadData(BaseModel):
    group_id: int
    inserted_count: int
    new_word_count: int
    strategy: str  # 寫入後依新詞數計算的策略名稱
```

- [ ] **Step 2：撰寫 `app/routers/hotword.py`**

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.exceptions import HotwordGroupNotFoundError
from app.core.response import success
from app.deps.auth import require_scope
from app.deps.db import get_db
from app.models import ApiKey
from app.repositories.hotword import HotwordGroupRepository, HotwordRepository
from app.schemas.common import ResponseEnvelope
from app.schemas.hotword import (
    HotwordBulkUploadData,
    HotwordBulkUploadRequest,
    HotwordGroupCreate,
    HotwordGroupData,
    HotwordGroupUpdate,
)
from app.services.hotword.dispatcher import select_strategy

router = APIRouter(prefix="/api/v1/hotword", tags=["hotword"])


def _to_data(group) -> HotwordGroupData:  # type: ignore[no-untyped-def]
    return HotwordGroupData(
        id=group.id,
        name=group.name,
        description=group.description,
        is_active=group.is_active,
        word_count=group.word_count,
        created_at=group.created_at,
        updated_at=group.updated_at,
    )


@router.post(
    "/groups",
    response_model=ResponseEnvelope[HotwordGroupData],
    status_code=status.HTTP_201_CREATED,
)
def create_group(
    payload: HotwordGroupCreate,
    api_key: ApiKey = Depends(require_scope("asr:write")),
    db: Session = Depends(get_db),
) -> ResponseEnvelope[HotwordGroupData]:
    repo = HotwordGroupRepository(db, api_key.id)
    group = repo.create(name=payload.name, description=payload.description)
    db.commit()
    return success(_to_data(group))


@router.get("/groups", response_model=ResponseEnvelope[list[HotwordGroupData]])
def list_groups(
    api_key: ApiKey = Depends(require_scope("asr:read")),
    db: Session = Depends(get_db),
    limit: int = 50,
    offset: int = 0,
) -> ResponseEnvelope[list[HotwordGroupData]]:
    repo = HotwordGroupRepository(db, api_key.id)
    groups = repo.list(limit=limit, offset=offset)
    return success([_to_data(g) for g in groups])


@router.get("/groups/{group_id}", response_model=ResponseEnvelope[HotwordGroupData])
def get_group(
    group_id: int,
    api_key: ApiKey = Depends(require_scope("asr:read")),
    db: Session = Depends(get_db),
) -> ResponseEnvelope[HotwordGroupData]:
    repo = HotwordGroupRepository(db, api_key.id)
    group = repo.get(group_id)
    if group is None:
        raise HotwordGroupNotFoundError(details={"group_id": group_id})
    return success(_to_data(group))


@router.put("/groups/{group_id}", response_model=ResponseEnvelope[HotwordGroupData])
def update_group(
    group_id: int,
    payload: HotwordGroupUpdate,
    api_key: ApiKey = Depends(require_scope("asr:write")),
    db: Session = Depends(get_db),
) -> ResponseEnvelope[HotwordGroupData]:
    repo = HotwordGroupRepository(db, api_key.id)
    group = repo.get(group_id)
    if group is None:
        raise HotwordGroupNotFoundError(details={"group_id": group_id})
    changes = payload.model_dump(exclude_unset=True)
    if changes:
        repo.update(group, **changes)
    db.commit()
    return success(_to_data(group))


@router.delete(
    "/groups/{group_id}",
    response_model=ResponseEnvelope[None],
    status_code=status.HTTP_200_OK,
)
def delete_group(
    group_id: int,
    api_key: ApiKey = Depends(require_scope("asr:write")),
    db: Session = Depends(get_db),
) -> ResponseEnvelope[None]:
    repo = HotwordGroupRepository(db, api_key.id)
    group = repo.get(group_id)
    if group is None:
        raise HotwordGroupNotFoundError(details={"group_id": group_id})
    repo.delete(group)
    db.commit()
    return success(None)


@router.post(
    "/groups/{group_id}/words/bulk",
    response_model=ResponseEnvelope[HotwordBulkUploadData],
    status_code=status.HTTP_201_CREATED,
)
def bulk_upload_words(
    group_id: int,
    payload: HotwordBulkUploadRequest,
    api_key: ApiKey = Depends(require_scope("asr:write")),
    db: Session = Depends(get_db),
) -> ResponseEnvelope[HotwordBulkUploadData]:
    group_repo = HotwordGroupRepository(db, api_key.id)
    group = group_repo.get(group_id)
    if group is None:
        raise HotwordGroupNotFoundError(details={"group_id": group_id})
    word_repo = HotwordRepository(db, api_key.id)
    inserted = word_repo.bulk_insert(
        group_id,
        [w.model_dump() for w in payload.words],
    )
    group_repo.refresh_word_count(group_id)
    db.commit()
    strategy = select_strategy(group_id, db, api_key.id)
    return success(
        HotwordBulkUploadData(
            group_id=group_id,
            inserted_count=inserted,
            new_word_count=group.word_count,
            strategy=strategy.name,
        )
    )
```

- [ ] **Step 3：ruff + mypy**

```powershell
cd D:\Qwen_asr\backend
.\.venv\Scripts\ruff.exe check app
.\.venv\Scripts\mypy.exe app
```

預期：全綠。

- [ ] **Step 4：Commit**

```powershell
cd D:\Qwen_asr
git add backend/app/schemas/hotword.py backend/app/routers/hotword.py
git commit -m "$(@'
feat(m5): 加入 Hotword router 6 個端點與 schemas

端點清單：
- POST /api/v1/hotword/groups（require asr:write）
- GET /api/v1/hotword/groups（require asr:read）
- GET /api/v1/hotword/groups/:id
- PUT /api/v1/hotword/groups/:id
- DELETE /api/v1/hotword/groups/:id
- POST /api/v1/hotword/groups/:id/words/bulk（含 strategy 名稱回傳）

特徵：
- 所有路由 ResponseEnvelope[T] + require_scope
- bulk_upload 含 max_length=2000 防護
- bulk_upload 完成後 refresh_word_count 並回傳 dispatcher 選出的 strategy 名

對應計劃：M5 Task 5.5
對應規格：v1.9 §3.4

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
'@)"
```

---

## Task 5.6：Dataset Service + schemas

**Files:**
- Create: `backend/app/services/dataset/__init__.py`
- Create: `backend/app/services/dataset/sample_processor.py`
- Create: `backend/app/schemas/dataset.py`

- [ ] **Step 1：建立目錄**

```powershell
cd D:\Qwen_asr\backend
New-Item app/services/dataset -ItemType Directory -Force
```

- [ ] **Step 2：撰寫 `app/services/dataset/sample_processor.py`**

```python
"""Dataset 樣本處理：MIME 校驗 → UUID 儲存 → 16 kHz 重取樣 → 寫入 audio_files。"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import DatasetSampleInvalidError
from app.models import AudioFile
from app.repositories.audio_file import AudioFileRepository
from app.services.audio.mime import verify_mime
from app.services.audio.resampler import resample_to_16k_mono
from app.services.audio.storage import store_upload


async def process_sample(
    *,
    db: Session,
    api_key_id: int,
    raw_bytes: bytes,
    original_name: str,
    transcript: str,
    settings: Settings,
) -> tuple[AudioFile, float]:
    """處理單一樣本，回傳 (audio_file, duration_sec)。

    Raises:
        AudioMimeInvalidError / AudioStorageFailedError / AudioResampleFailedError
        DatasetSampleInvalidError: transcript 為空或過長
    """
    if not transcript.strip():
        raise DatasetSampleInvalidError(message="樣本 transcript 不可為空")
    if len(transcript) > 5000:
        raise DatasetSampleInvalidError(
            message=f"樣本 transcript 超過 5000 字（實際 {len(transcript)}）"
        )

    mime, ext = verify_mime(raw_bytes, settings.supported_formats_list)
    audio = store_upload(
        db=db,
        api_key_id=api_key_id,
        raw_bytes=raw_bytes,
        original_name=original_name,
        canonical_ext=ext,
        verified_mime=mime,
        storage_dir=settings.AUDIO_STORAGE_DIR,
    )
    db.commit()

    resample = await resample_to_16k_mono(
        Path(audio.storage_path),
        settings.AUDIO_STORAGE_DIR / "dataset_processed",
    )
    AudioFileRepository(db, api_key_id).update_after_resample(
        audio.id,
        original_sample_rate=resample.original_sample_rate,
        duration_sec=resample.duration_sec,
    )
    db.commit()
    return audio, resample.duration_sec
```

- [ ] **Step 3：撰寫 `app/services/dataset/__init__.py`**

```python
from app.services.dataset.sample_processor import process_sample

__all__ = ["process_sample"]
```

- [ ] **Step 4：撰寫 `app/schemas/dataset.py`**

```python
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DatasetCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    metadata: dict[str, Any] | None = None


class DatasetData(BaseModel):
    id: int
    name: str
    description: str | None
    sample_count: int
    total_duration_sec: float
    metadata: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class DatasetSampleData(BaseModel):
    id: int
    dataset_id: int
    audio_file_id: int
    transcript: str
    duration_sec: float
    file_size: int
    created_at: datetime
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
git add backend/app/services/dataset backend/app/schemas/dataset.py
git commit -m "$(@'
feat(m5): 加入 Dataset 樣本處理服務與 schemas

- services/dataset/sample_processor.py：
  - process_sample 整合 M3 既有 pipeline
  - MIME 校驗 → store_upload → 16k 重取樣 → 寫回 audio_files
  - transcript 驗證（非空 / ≤ 5000 字）→ DatasetSampleInvalidError
- schemas/dataset.py：DatasetCreate / DatasetData / DatasetSampleData

對應計劃：M5 Task 5.6
對應設計：Phase 2 design §3.1 Dataset 樣本驗證

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
'@)"
```

---

## Task 5.7：Dataset router（4 端點）

**Files:**
- Create: `backend/app/routers/dataset.py`

- [ ] **Step 1：撰寫 `app/routers/dataset.py`**

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import DatasetNotFoundError
from app.core.response import success
from app.deps.auth import require_scope
from app.deps.db import get_db
from app.models import ApiKey
from app.repositories.dataset import DatasetRepository, DatasetSampleRepository
from app.schemas.common import ResponseEnvelope
from app.schemas.dataset import DatasetCreate, DatasetData, DatasetSampleData
from app.services.dataset import process_sample

router = APIRouter(prefix="/api/v1/dataset", tags=["dataset"])


def _to_data(dataset) -> DatasetData:  # type: ignore[no-untyped-def]
    return DatasetData(
        id=dataset.id,
        name=dataset.name,
        description=dataset.description,
        sample_count=dataset.sample_count,
        total_duration_sec=dataset.total_duration_sec,
        metadata=dataset.metadata_,
        created_at=dataset.created_at,
        updated_at=dataset.updated_at,
    )


def _to_sample_data(sample) -> DatasetSampleData:  # type: ignore[no-untyped-def]
    return DatasetSampleData(
        id=sample.id,
        dataset_id=sample.dataset_id,
        audio_file_id=sample.audio_file_id,
        transcript=sample.transcript,
        duration_sec=sample.duration_sec,
        file_size=sample.file_size,
        created_at=sample.created_at,
    )


@router.post(
    "",
    response_model=ResponseEnvelope[DatasetData],
    status_code=status.HTTP_201_CREATED,
)
def create_dataset(
    payload: DatasetCreate,
    api_key: ApiKey = Depends(require_scope("asr:write")),
    db: Session = Depends(get_db),
) -> ResponseEnvelope[DatasetData]:
    repo = DatasetRepository(db, api_key.id)
    dataset = repo.create(
        name=payload.name,
        description=payload.description,
        metadata_=payload.metadata,
    )
    db.commit()
    return success(_to_data(dataset))


@router.get("", response_model=ResponseEnvelope[list[DatasetData]])
def list_datasets(
    api_key: ApiKey = Depends(require_scope("asr:read")),
    db: Session = Depends(get_db),
    limit: int = 50,
    offset: int = 0,
) -> ResponseEnvelope[list[DatasetData]]:
    repo = DatasetRepository(db, api_key.id)
    datasets = repo.list(limit=limit, offset=offset)
    return success([_to_data(d) for d in datasets])


@router.post(
    "/{dataset_id}/samples",
    response_model=ResponseEnvelope[DatasetSampleData],
    status_code=status.HTTP_201_CREATED,
)
async def upload_sample(
    dataset_id: int,
    file: UploadFile = File(...),
    transcript: str = Form(...),
    api_key: ApiKey = Depends(require_scope("asr:write")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ResponseEnvelope[DatasetSampleData]:
    dataset_repo = DatasetRepository(db, api_key.id)
    dataset = dataset_repo.get(dataset_id)
    if dataset is None:
        raise DatasetNotFoundError(details={"dataset_id": dataset_id})

    raw_bytes = await file.read()
    audio, duration_sec = await process_sample(
        db=db,
        api_key_id=api_key.id,
        raw_bytes=raw_bytes,
        original_name=file.filename or "sample.wav",
        transcript=transcript,
        settings=settings,
    )

    sample_repo = DatasetSampleRepository(db, api_key.id)
    sample = sample_repo.create(
        dataset_id=dataset_id,
        audio_file_id=audio.id,
        transcript=transcript,
        duration_sec=duration_sec,
        file_size=len(raw_bytes),
    )
    dataset_repo.refresh_stats(dataset_id)
    db.commit()
    return success(_to_sample_data(sample))


@router.get(
    "/{dataset_id}/samples",
    response_model=ResponseEnvelope[list[DatasetSampleData]],
)
def list_samples(
    dataset_id: int,
    api_key: ApiKey = Depends(require_scope("asr:read")),
    db: Session = Depends(get_db),
    limit: int = 50,
    offset: int = 0,
) -> ResponseEnvelope[list[DatasetSampleData]]:
    dataset_repo = DatasetRepository(db, api_key.id)
    dataset = dataset_repo.get(dataset_id)
    if dataset is None:
        raise DatasetNotFoundError(details={"dataset_id": dataset_id})
    sample_repo = DatasetSampleRepository(db, api_key.id)
    samples = sample_repo.list_by_dataset(dataset_id, limit=limit, offset=offset)
    return success([_to_sample_data(s) for s in samples])
```

- [ ] **Step 2：ruff + mypy**

```powershell
cd D:\Qwen_asr\backend
.\.venv\Scripts\ruff.exe check app
.\.venv\Scripts\mypy.exe app
```

預期：全綠。

- [ ] **Step 3：Commit**

```powershell
cd D:\Qwen_asr
git add backend/app/routers/dataset.py
git commit -m "$(@'
feat(m5): 加入 Dataset router 4 個端點

端點清單：
- POST /api/v1/dataset
- GET /api/v1/dataset
- POST /api/v1/dataset/:id/samples（multipart upload + 自動 MIME / store / resample）
- GET /api/v1/dataset/:id/samples（含 limit / offset）

特徵：
- upload_sample 觸發 process_sample 完整 pipeline
- 寫入 dataset_samples 後 refresh_stats（sample_count / total_duration_sec 快取）
- 列表 API 大欄位排除（transcript 屬合理大小不額外處理）

對應計劃：M5 Task 5.7

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
'@)"
```

---

## Task 5.8：main.py 整合 + 整合測試

**Files:**
- Modify: `backend/app/main.py`
- Create: `backend/tests/integration/test_hotword_router.py`
- Create: `backend/tests/integration/test_dataset_router.py`

- [ ] **Step 1：修改 `app/main.py` 加入 hotword / dataset router**

讀取 `app/main.py`，在 `from app.routers.asr import router as asr_router` 之後加：

```python
from app.routers.dataset import router as dataset_router
from app.routers.hotword import router as hotword_router
```

在 `app.include_router(asr_router)` 之後加：

```python
    app.include_router(hotword_router)
    app.include_router(dataset_router)
```

- [ ] **Step 2：撰寫 `tests/integration/test_hotword_router.py`**

```python
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.security import derive_hmac_key, hash_token, lookup_prefix
from app.deps.db import get_db
from app.middleware import register_exception_handlers
from app.routers.hotword import router as hotword_router


def _build_app(db_session: Session) -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(hotword_router)
    app.dependency_overrides[get_db] = lambda: db_session
    return app


@pytest.fixture
def hotword_app(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> tuple[FastAPI, str]:
    monkeypatch.setenv("API_KEY", "hotword-test")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@h/d")
    monkeypatch.setenv("DB_PASSWORD", "p")
    monkeypatch.setenv("THIRD_PARTY_LICENSE_ACK", "true")
    from app.core.config import get_settings
    get_settings.cache_clear()

    raw_token = "hw-token-abc"
    hmac_key = derive_hmac_key("hotword-test")
    db_session.execute(text("TRUNCATE api_keys, hotword_groups, hotwords CASCADE"))
    db_session.execute(
        text(
            "INSERT INTO api_keys (key_hash, lookup_prefix, name, scopes) "
            "VALUES (:h, :p, 'hwk', '{asr:read,asr:write}')"
        ),
        {"h": hash_token(raw_token), "p": lookup_prefix(raw_token, hmac_key)},
    )
    db_session.commit()
    return _build_app(db_session), raw_token


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_create_group_returns_201(hotword_app) -> None:
    app, token = hotword_app
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/hotword/groups",
            json={"name": "客戶名單", "description": "VIP"},
            headers=_headers(token),
        )
    assert resp.status_code == 201
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["name"] == "客戶名單"
    assert body["data"]["word_count"] == 0


def test_list_groups_returns_envelope(hotword_app) -> None:
    app, token = hotword_app
    with TestClient(app) as client:
        client.post(
            "/api/v1/hotword/groups",
            json={"name": "g1"},
            headers=_headers(token),
        )
        client.post(
            "/api/v1/hotword/groups",
            json={"name": "g2"},
            headers=_headers(token),
        )
        resp = client.get("/api/v1/hotword/groups", headers=_headers(token))
    assert resp.status_code == 200
    assert len(resp.json()["data"]) == 2


def test_get_group_not_found(hotword_app) -> None:
    app, token = hotword_app
    with TestClient(app) as client:
        resp = client.get("/api/v1/hotword/groups/9999", headers=_headers(token))
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "HOTWORD_GROUP_NOT_FOUND"


def test_update_group(hotword_app) -> None:
    app, token = hotword_app
    with TestClient(app) as client:
        create_resp = client.post(
            "/api/v1/hotword/groups",
            json={"name": "old-name"},
            headers=_headers(token),
        )
        group_id = create_resp.json()["data"]["id"]
        resp = client.put(
            f"/api/v1/hotword/groups/{group_id}",
            json={"name": "new-name"},
            headers=_headers(token),
        )
    assert resp.status_code == 200
    assert resp.json()["data"]["name"] == "new-name"


def test_delete_group(hotword_app) -> None:
    app, token = hotword_app
    with TestClient(app) as client:
        create_resp = client.post(
            "/api/v1/hotword/groups",
            json={"name": "to-delete"},
            headers=_headers(token),
        )
        group_id = create_resp.json()["data"]["id"]
        resp = client.delete(
            f"/api/v1/hotword/groups/{group_id}", headers=_headers(token)
        )
        get_resp = client.get(
            f"/api/v1/hotword/groups/{group_id}", headers=_headers(token)
        )
    assert resp.status_code == 200
    assert get_resp.status_code == 404


def test_bulk_upload_shallow_fusion(hotword_app) -> None:
    app, token = hotword_app
    with TestClient(app) as client:
        create_resp = client.post(
            "/api/v1/hotword/groups",
            json={"name": "vip"},
            headers=_headers(token),
        )
        group_id = create_resp.json()["data"]["id"]
        resp = client.post(
            f"/api/v1/hotword/groups/{group_id}/words/bulk",
            json={"words": [{"word": f"客戶{i}"} for i in range(50)]},
            headers=_headers(token),
        )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["inserted_count"] == 50
    assert data["new_word_count"] == 50
    assert data["strategy"] == "shallow_fusion"


def test_bulk_upload_ctc_ws(hotword_app) -> None:
    app, token = hotword_app
    with TestClient(app) as client:
        create_resp = client.post(
            "/api/v1/hotword/groups",
            json={"name": "medium"},
            headers=_headers(token),
        )
        group_id = create_resp.json()["data"]["id"]
        resp = client.post(
            f"/api/v1/hotword/groups/{group_id}/words/bulk",
            json={"words": [{"word": f"w{i}"} for i in range(500)]},
            headers=_headers(token),
        )
    assert resp.status_code == 201
    assert resp.json()["data"]["strategy"] == "ctc_ws"


def test_bulk_upload_too_large(hotword_app) -> None:
    app, token = hotword_app
    with TestClient(app) as client:
        create_resp = client.post(
            "/api/v1/hotword/groups",
            json={"name": "huge"},
            headers=_headers(token),
        )
        group_id = create_resp.json()["data"]["id"]
        resp = client.post(
            f"/api/v1/hotword/groups/{group_id}/words/bulk",
            json={"words": [{"word": f"w{i}"} for i in range(1000)]},
            headers=_headers(token),
        )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "HOTWORD_TOO_LARGE"


def test_unauthenticated_returns_401(hotword_app) -> None:
    app, _ = hotword_app
    with TestClient(app) as client:
        resp = client.get("/api/v1/hotword/groups")
    assert resp.status_code == 401
```

- [ ] **Step 3：撰寫 `tests/integration/test_dataset_router.py`**

```python
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.security import derive_hmac_key, hash_token, lookup_prefix
from app.deps.db import get_db
from app.middleware import register_exception_handlers
from app.routers.dataset import router as dataset_router

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "audio"


def _build_app(db_session: Session) -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(dataset_router)
    app.dependency_overrides[get_db] = lambda: db_session
    return app


@pytest.fixture
def dataset_app(
    db_session: Session, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> tuple[FastAPI, str]:
    monkeypatch.setenv("API_KEY", "dataset-test")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@h/d")
    monkeypatch.setenv("DB_PASSWORD", "p")
    monkeypatch.setenv("THIRD_PARTY_LICENSE_ACK", "true")
    monkeypatch.setenv("AUDIO_STORAGE_DIR", str(tmp_path))
    monkeypatch.setenv("SUPPORTED_AUDIO_FORMATS", "wav,mp3")
    from app.core.config import get_settings
    get_settings.cache_clear()

    raw_token = "ds-token-xyz"
    hmac_key = derive_hmac_key("dataset-test")
    db_session.execute(
        text("TRUNCATE api_keys, datasets, dataset_samples, audio_files CASCADE")
    )
    db_session.execute(
        text(
            "INSERT INTO api_keys (key_hash, lookup_prefix, name, scopes) "
            "VALUES (:h, :p, 'dsk', '{asr:read,asr:write}')"
        ),
        {"h": hash_token(raw_token), "p": lookup_prefix(raw_token, hmac_key)},
    )
    db_session.commit()
    return _build_app(db_session), raw_token


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_create_dataset(dataset_app) -> None:
    app, token = dataset_app
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/dataset",
            json={"name": "ds1", "description": "test"},
            headers=_headers(token),
        )
    assert resp.status_code == 201
    body = resp.json()
    assert body["data"]["sample_count"] == 0
    assert body["data"]["total_duration_sec"] == 0.0


def test_upload_sample_pipeline(dataset_app) -> None:
    app, token = dataset_app
    with TestClient(app) as client:
        create_resp = client.post(
            "/api/v1/dataset",
            json={"name": "ds1"},
            headers=_headers(token),
        )
        dataset_id = create_resp.json()["data"]["id"]
        with (FIXTURES / "valid_16k_mono.wav").open("rb") as f:
            resp = client.post(
                f"/api/v1/dataset/{dataset_id}/samples",
                files={"file": ("sample.wav", f, "audio/wav")},
                data={"transcript": "你好世界"},
                headers=_headers(token),
            )
    assert resp.status_code == 201
    body = resp.json()
    assert body["data"]["transcript"] == "你好世界"
    assert body["data"]["duration_sec"] > 0


def test_upload_sample_dataset_not_found(dataset_app) -> None:
    app, token = dataset_app
    with TestClient(app) as client:
        with (FIXTURES / "valid_16k_mono.wav").open("rb") as f:
            resp = client.post(
                "/api/v1/dataset/9999/samples",
                files={"file": ("sample.wav", f, "audio/wav")},
                data={"transcript": "test"},
                headers=_headers(token),
            )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "DATASET_NOT_FOUND"


def test_upload_sample_empty_transcript(dataset_app) -> None:
    app, token = dataset_app
    with TestClient(app) as client:
        create_resp = client.post(
            "/api/v1/dataset", json={"name": "ds1"}, headers=_headers(token)
        )
        dataset_id = create_resp.json()["data"]["id"]
        with (FIXTURES / "valid_16k_mono.wav").open("rb") as f:
            resp = client.post(
                f"/api/v1/dataset/{dataset_id}/samples",
                files={"file": ("sample.wav", f, "audio/wav")},
                data={"transcript": "   "},
                headers=_headers(token),
            )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "DATASET_SAMPLE_INVALID"


def test_upload_sample_rejects_zip_disguised(dataset_app) -> None:
    app, token = dataset_app
    with TestClient(app) as client:
        create_resp = client.post(
            "/api/v1/dataset", json={"name": "ds1"}, headers=_headers(token)
        )
        dataset_id = create_resp.json()["data"]["id"]
        with (FIXTURES / "fake_extension.wav.zip").open("rb") as f:
            resp = client.post(
                f"/api/v1/dataset/{dataset_id}/samples",
                files={"file": ("sample.wav", f, "audio/wav")},
                data={"transcript": "test"},
                headers=_headers(token),
            )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "AUDIO_MIME_INVALID"


def test_list_samples(dataset_app) -> None:
    app, token = dataset_app
    with TestClient(app) as client:
        create_resp = client.post(
            "/api/v1/dataset", json={"name": "ds1"}, headers=_headers(token)
        )
        dataset_id = create_resp.json()["data"]["id"]
        with (FIXTURES / "valid_16k_mono.wav").open("rb") as f:
            client.post(
                f"/api/v1/dataset/{dataset_id}/samples",
                files={"file": ("a.wav", f, "audio/wav")},
                data={"transcript": "句子 1"},
                headers=_headers(token),
            )
        resp = client.get(
            f"/api/v1/dataset/{dataset_id}/samples", headers=_headers(token)
        )
    assert resp.status_code == 200
    assert len(resp.json()["data"]) == 1
```

- [ ] **Step 4：執行整合測試**

```powershell
cd D:\Qwen_asr\backend
.\.venv\Scripts\pytest.exe tests/integration/test_hotword_router.py tests/integration/test_dataset_router.py -v
```

預期：9 hotword + 6 dataset = 15 個測試 PASS。

- [ ] **Step 5：跑全套測試確保無回歸**

```powershell
.\.venv\Scripts\pytest.exe -v --cov=app --cov-fail-under=70 --no-header -q 2>&1 | tail -30
```

預期：M1+M2+M3+M4 既有 106 + M5 新增 ~25 = ~130 個 PASS。

- [ ] **Step 6：docker compose 啟動驗證**

```powershell
cd D:\Qwen_asr
@"
API_KEY=m5-integ-token
DB_PASSWORD=m5-integ-db
THIRD_PARTY_LICENSE_ACK=true
"@ | Out-File -Encoding utf8 .env -NoNewline

docker compose up -d postgres
Start-Sleep -Seconds 20

cd backend
$env:DATABASE_URL = "postgresql+psycopg://qwasr:m5-integ-db@localhost:5432/qwen_asr"
.\.venv\Scripts\alembic.exe upgrade head

cd ..
docker compose up -d asr-backend
Start-Sleep -Seconds 30
docker compose logs asr-backend --tail 20
docker compose ps

# 拆除
docker compose down -v
Remove-Item .env
```

預期：backend 顯示「ASR consumer started」並 healthy；alembic 列出 9 個表（M1 5 + M5 4）。

- [ ] **Step 7：Commit**

```powershell
cd D:\Qwen_asr
git add backend/app/main.py backend/tests/integration/test_hotword_router.py backend/tests/integration/test_dataset_router.py
git commit -m "$(@'
feat(m5): main.py 整合 + 端到端整合測試（hotword 9 + dataset 6）

- main.py 補 include_router(hotword_router) / include_router(dataset_router)
- test_hotword_router.py：9 個整合測試
  - CRUD 5 個 + bulk_upload 3 個（< 100 / 100-1000 / ≥ 1000）+ unauthenticated 401
- test_dataset_router.py：6 個整合測試
  - 建立 / 上傳 sample / 不存在 dataset / 空 transcript / zip 偽裝 / list

驗收：
- 全套測試 ~130 PASS（M4 106 + M5 ~25）
- docker compose 完整啟動

對應計劃：M5 Task 5.8
對應規格：v1.9 §3.4 完整 10 個 M5 端點

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
'@)"
```

---

## Self-Review

**1. Spec coverage（對照設計文件 §3.1）：**

| 設計章節 | 對應 Task |
|---------|----------|
| §3.1 範圍：Hotword 三層 + Dataset CRUD | 全部 |
| §3.1 關鍵元件 1：三層分流決策器 | T5.4 |
| §3.1 關鍵元件 2：Dataset 樣本驗證 | T5.6 |
| §3.1 API 端點 6 + 4 個 | T5.5 + T5.7 |
| §3.1 DoD：10 端點 PASS | T5.8 |
| §3.1 DoD：Hotword 規模分流三組 | T5.4 + T5.8 |
| §3.1 DoD：ENV 覆寫閾值 | T5.4 Step 5 |
| §3.1 依賴：M2 Tenant Isolation | 所有 repo |
| §3.1 依賴：M3 verify_mime / store / resample | T5.6 |
| §4.5 三層架構切換邏輯 | T5.4 |
| §4.9 4 個新錯誤碼 | T5.2 |
| §5 0002 migration | T5.1 |
| §6 端點清單 | T5.5 + T5.7 |
| §7 ENV 新增 HOTWORD_*_THRESHOLD | T5.4 |
| §10 強制規範對齊（1, 2, 5, 6, 7, 8-10, 18, 20） | 全部 |

**2. Placeholder scan：** 已搜尋 `TBD` / `TODO` / `implement later` / `fill in details` / `add appropriate error handling` / `similar to Task N` — 無命中。所有 code block 為實際可執行內容。

**3. Type consistency：**
- `HotwordGroup.word_count` 在 model（T5.1）、repository `refresh_word_count`（T5.3）、router bulk_upload 回傳（T5.5）三處欄位名一致
- `HotwordContext` 結構在 strategies（T5.4）與 ABC 一致
- `process_sample` 回傳 `(audio, duration_sec)` 在 service（T5.6）與 router（T5.7）解構一致
- `DatasetSampleData` 欄位在 schema、router `_to_sample_data` 完整對齊

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-16-phase2-m5-hotword-dataset.md`. M5 含 8 個 task 約 1700 行。

**1. Subagent-Driven（推薦）** — 每個 task 分派 fresh subagent + 兩階段審查
**2. Inline Execution** — 在當前 session 跑

**M6-M11 plan 待 M5 完成後再撰寫。** 也可一次寫齊 7 份 plan 後再執行（會延後 M5 啟動但避免設計漂移）。
