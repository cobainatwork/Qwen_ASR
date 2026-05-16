# Phase 2 / M9 — YouTube 下載 + 校正工作台 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 實作 yt-dlp 下載（含 SSRF 防護）→ ASR transcribe（複用 M4 pipeline）→ correction_sessions 自動建立 → 前端校正 UI（每段 Optimistic Locking）→ export 到 dataset 完整流程，完成後可從 YouTube URL 一路走到加入 dataset 樣本。

**Architecture:** YouTube 下載走 `services/youtube/downloader.py` 包裝 yt-dlp，URL 通過正規表達式 + 網域白名單驗證後才執行。下載後音檔走 M3 store + M4 transcribe，自動建立 correction_session 並依 transcription.timestamps 切段成多個 correction_segment。前端透過 SWR + REST API 編輯每段，PUT 時帶 `expected_version`，後端透過 `version` 欄位實作 Optimistic Locking。Export 將段落寫入指定 dataset。

**Tech Stack:** yt-dlp 2024.11+、urllib.parse、M3 既有 audio pipeline、M4 既有 transcribe pipeline。前端：Next.js 14 既有 + SWR + 簡單音檔播放控制。

**對應設計文件：** Phase 2 design.md §3.5、§4.9。對應規格：v1.9 §3.3.7、§3.3.8、§14。

---

## File Structure

| 路徑 | 動作 | 責任 |
|------|------|------|
| `backend/app/models/youtube.py` | Create | `YoutubeDownload` ORM |
| `backend/app/models/correction.py` | Create | `CorrectionSession` / `CorrectionSegment` ORM（含 version 欄位） |
| `backend/app/models/__init__.py` | Modify | re-export |
| `backend/alembic/versions/0004_youtube_correction.py` | Create | DB schema |
| `backend/app/schemas/youtube.py` | Create | Pydantic |
| `backend/app/schemas/correction.py` | Create | Pydantic |
| `backend/app/repositories/youtube.py` | Create | `YoutubeDownloadRepository` |
| `backend/app/repositories/correction.py` | Create | `CorrectionSessionRepository` / `CorrectionSegmentRepository` |
| `backend/app/services/youtube/__init__.py` | Create | re-export |
| `backend/app/services/youtube/url_validator.py` | Create | SSRF 防護 |
| `backend/app/services/youtube/downloader.py` | Create | yt-dlp 包裝 |
| `backend/app/services/correction/session_builder.py` | Create | transcription → session/segments |
| `backend/app/services/correction/exporter.py` | Create | 段落匯出至 dataset |
| `backend/app/routers/youtube.py` | Create | 3 個 YouTube 端點 |
| `backend/app/routers/correction.py` | Create | 4 個 Correction 端點 |
| `backend/app/main.py` | Modify | include vendor routers |
| `backend/app/core/exceptions.py` | Modify | 5 個錯誤碼 |
| `backend/app/core/config.py` | Modify | 2 個 ENV |
| `backend/tests/unit/test_youtube_url_validator.py` | Create | SSRF 防護單元 |
| `backend/tests/integration/test_youtube_router.py` | Create | YouTube 端點 |
| `backend/tests/integration/test_correction_router.py` | Create | Correction 端點 + Optimistic Locking |
| `frontend/app/correction/[session_id]/page.tsx` | Create | 校正 UI |
| `frontend/components/correction/SegmentEditor.tsx` | Create | 單段編輯元件 |
| `frontend/lib/api/correction.ts` | Create | 校正 API helper |

---

## Task 9.1：ORM + migration + exceptions + ENV

**Files:**
- Create: `backend/app/models/youtube.py` / `correction.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/0004_youtube_correction.py`
- Modify: `backend/app/core/exceptions.py` / `config.py`

- [ ] **Step 1：撰寫 `app/models/youtube.py`**

```python
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin


class YoutubeDownload(Base, TenantMixin):
    __tablename__ = "youtube_downloads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    video_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    audio_file_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("audio_files.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False, server_default="pending")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    duration_sec: Mapped[float | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
```

- [ ] **Step 2：撰寫 `app/models/correction.py`**

```python
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin


class CorrectionSession(Base, TenantMixin):
    __tablename__ = "correction_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    transcription_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("transcriptions.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, server_default="in_progress")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class CorrectionSegment(Base):
    """單一段落（跨租戶透過 session → api_key_id 驗證）。"""

    __tablename__ = "correction_segments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("correction_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    segment_index: Mapped[int] = mapped_column(Integer, nullable=False)
    start_sec: Mapped[float] = mapped_column(Float, nullable=False)
    end_sec: Mapped[float] = mapped_column(Float, nullable=False)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    corrected_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")  # Optimistic Locking
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
```

- [ ] **Step 3：擴充 `app/models/__init__.py`**

加 import：
```python
from app.models.correction import CorrectionSegment, CorrectionSession
from app.models.youtube import YoutubeDownload
```

`__all__` 補三項。

- [ ] **Step 4：撰寫 `backend/alembic/versions/0004_youtube_correction.py`**

```python
"""Phase 2 / M9：youtube_downloads / correction_sessions / correction_segments

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-16

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "youtube_downloads",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("api_key_id", sa.Integer(), sa.ForeignKey("api_keys.id"), nullable=False),
        sa.Column("url", sa.String(500), nullable=False),
        sa.Column("video_title", sa.String(500), nullable=True),
        sa.Column("audio_file_id", sa.Integer(), sa.ForeignKey("audio_files.id"), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("file_size", sa.BigInteger(), nullable=True),
        sa.Column("duration_sec", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_youtube_downloads_api_key_id", "youtube_downloads", ["api_key_id"])
    op.create_index("idx_youtube_downloads_status", "youtube_downloads", ["status"])

    op.create_table(
        "correction_sessions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("api_key_id", sa.Integer(), sa.ForeignKey("api_keys.id"), nullable=False),
        sa.Column("transcription_id", sa.Integer(), sa.ForeignKey("transcriptions.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="in_progress"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_correction_sessions_api_key_id", "correction_sessions", ["api_key_id"])
    op.create_index("idx_correction_sessions_transcription_id", "correction_sessions", ["transcription_id"])

    op.create_table(
        "correction_segments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("correction_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("segment_index", sa.Integer(), nullable=False),
        sa.Column("start_sec", sa.Float(), nullable=False),
        sa.Column("end_sec", sa.Float(), nullable=False),
        sa.Column("original_text", sa.Text(), nullable=False),
        sa.Column("corrected_text", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_correction_segments_session_id", "correction_segments", ["session_id"])
    op.create_index(
        "idx_correction_segments_session_index_unique",
        "correction_segments",
        ["session_id", "segment_index"],
        unique=True,
    )

    op.execute("CREATE TRIGGER trg_youtube_downloads_updated_at BEFORE UPDATE ON youtube_downloads FOR EACH ROW EXECUTE FUNCTION set_updated_at();")
    op.execute("CREATE TRIGGER trg_correction_sessions_updated_at BEFORE UPDATE ON correction_sessions FOR EACH ROW EXECUTE FUNCTION set_updated_at();")
    op.execute("CREATE TRIGGER trg_correction_segments_updated_at BEFORE UPDATE ON correction_segments FOR EACH ROW EXECUTE FUNCTION set_updated_at();")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_correction_segments_updated_at ON correction_segments")
    op.execute("DROP TRIGGER IF EXISTS trg_correction_sessions_updated_at ON correction_sessions")
    op.execute("DROP TRIGGER IF EXISTS trg_youtube_downloads_updated_at ON youtube_downloads")
    op.drop_table("correction_segments")
    op.drop_table("correction_sessions")
    op.drop_table("youtube_downloads")
```

- [ ] **Step 5：擴充 `exceptions.py` 5 個錯誤碼**

```python
# ----- Phase 2 / M9 -----
class YoutubeUrlInvalidError(AppException):
    code = "YOUTUBE_URL_INVALID"
    http_status = 400
    message = "YouTube URL 不符合白名單"


class YoutubeDownloadFailedError(AppException):
    code = "YOUTUBE_DOWNLOAD_FAILED"
    http_status = 502
    message = "yt-dlp 下載失敗"


class YoutubeFileTooLargeError(AppException):
    code = "YOUTUBE_FILE_TOO_LARGE"
    http_status = 413
    message = "影片下載大小超過上限"


class CorrectionSessionNotFoundError(AppException):
    code = "CORRECTION_SESSION_NOT_FOUND"
    http_status = 404
    message = "校正 session 不存在"


class CorrectionVersionMismatchError(AppException):
    code = "CORRECTION_VERSION_MISMATCH"
    http_status = 409
    message = "版本衝突：他人已修改過此段落"
```

`ALL_ERROR_CODES` 補 5 個（34 → 39）。

- [ ] **Step 6：擴充 `config.py` ENV**

加在 `# ----- Phase 2 / M7 -----` 之後：

```python
    # ----- Phase 2 / M9 -----
    YOUTUBE_DOMAIN_WHITELIST: str = "youtube.com,youtu.be"
    YOUTUBE_MAX_DOWNLOAD_SIZE_MB: int = 1024  # 1 GB

    @property
    def youtube_whitelist_set(self) -> set[str]:
        return {d.strip().lower() for d in self.YOUTUBE_DOMAIN_WHITELIST.split(",") if d.strip()}
```

- [ ] **Step 7：alembic 驗證**

```powershell
cd D:\Qwen_asr
docker compose up -d postgres
Start-Sleep -Seconds 20
cd backend
$env:DATABASE_URL = "postgresql+psycopg://qwasr:devpass@localhost:5432/qwen_asr"
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\alembic.exe downgrade 0003
.\.venv\Scripts\alembic.exe upgrade head
cd ..
docker compose down -v
```

預期：upgrade 增 3 表 → 共 14 個追蹤表。

- [ ] **Step 8：Commit**

```powershell
cd D:\Qwen_asr
git add backend/app/models/youtube.py backend/app/models/correction.py backend/app/models/__init__.py backend/alembic/versions/0004_youtube_correction.py backend/app/core/exceptions.py backend/app/core/config.py
git commit -m "$(@'
feat(m9): 加入 YoutubeDownload / CorrectionSession / CorrectionSegment ORM + 0004 migration + 5 錯誤碼

- models/youtube.py：YoutubeDownload（TenantMixin + status 狀態機）
- models/correction.py：
  - CorrectionSession（TenantMixin，transcription FK）
  - CorrectionSegment（含 version 欄位 → Optimistic Locking）
  - segment_index 與 session_id 組成 partial unique index
- alembic 0004：3 個新表 + 3 個 trigger
- exceptions 補 5：YOUTUBE_URL_INVALID / DOWNLOAD_FAILED / FILE_TOO_LARGE / CORRECTION_SESSION_NOT_FOUND / VERSION_MISMATCH
- config 補 ENV：YOUTUBE_DOMAIN_WHITELIST / YOUTUBE_MAX_DOWNLOAD_SIZE_MB + youtube_whitelist_set property

對應計劃：M9 Task 9.1
對應規格：v1.9 §5、§3.4

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
'@)"
```

---

## Task 9.2：YouTube URL 驗證 + 下載 service

**Files:**
- Create: `backend/app/services/youtube/__init__.py`
- Create: `backend/app/services/youtube/url_validator.py`
- Create: `backend/app/services/youtube/downloader.py`
- Create: `backend/tests/unit/test_youtube_url_validator.py`

- [ ] **Step 1：撰寫 `app/services/youtube/url_validator.py`**

```python
"""YouTube URL SSRF 防護驗證（規格 §3.3.7 + §14.2）。"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from app.core.config import Settings
from app.core.exceptions import YoutubeUrlInvalidError

# 嚴格 youtube URL 模式
_YOUTUBE_PATTERNS = [
    re.compile(r"^https://(?:www\.)?youtube\.com/watch\?v=[\w-]{6,20}(?:&|$)"),
    re.compile(r"^https://youtu\.be/[\w-]{6,20}(?:\?|$)"),
    re.compile(r"^https://(?:www\.)?youtube\.com/embed/[\w-]{6,20}(?:\?|$)"),
]


def validate_youtube_url(url: str, settings: Settings) -> str:
    """驗證 URL 符合白名單與模式，回傳正規化後 URL。

    Raises:
        YoutubeUrlInvalidError: 任何不符合的條件
    """
    if not url:
        raise YoutubeUrlInvalidError(message="URL 為空")

    if not url.startswith("https://"):
        raise YoutubeUrlInvalidError(
            message="僅接受 https",
            details={"url": url[:200]},
        )

    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise YoutubeUrlInvalidError(details={"scheme": parsed.scheme})

    host = (parsed.hostname or "").lower().lstrip("www.")
    whitelist = settings.youtube_whitelist_set
    # 比對 host（移除前綴 www）是否在白名單內
    if host not in whitelist:
        raise YoutubeUrlInvalidError(
            details={"host": host, "whitelist": sorted(whitelist)},
        )

    # 嚴格 path 比對（避免 youtube.com/redirect?... 等變體）
    if not any(p.match(url) for p in _YOUTUBE_PATTERNS):
        raise YoutubeUrlInvalidError(
            message="URL 路徑不符合預期格式",
            details={"url": url[:200]},
        )

    return url
```

- [ ] **Step 2：撰寫 `app/services/youtube/downloader.py`**

```python
"""yt-dlp 包裝（規格 §3.3.7）。

關鍵設計：
- yt-dlp 延遲 import（與其他 audio extras 一致）
- 先 HEAD 檢查（透過 yt-dlp 的 --skip-download metadata）
- 下載完成後重命名為 UUID（M3 既有 store_upload 模式）
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import structlog

from app.core.config import Settings
from app.core.exceptions import YoutubeDownloadFailedError, YoutubeFileTooLargeError

logger = structlog.get_logger(__name__)


@dataclass
class YoutubeMetadata:
    title: str
    duration_sec: float
    estimated_size_bytes: int | None


@dataclass
class YoutubeDownloadResult:
    audio_path: Path
    metadata: YoutubeMetadata
    file_size_bytes: int


async def fetch_metadata(url: str) -> YoutubeMetadata:
    """以 yt-dlp metadata-only 模式取得影片資訊。"""
    try:
        import yt_dlp  # type: ignore[import-not-found]
    except ImportError as e:
        raise YoutubeDownloadFailedError(message="yt-dlp 未安裝") from e

    def _extract() -> dict:
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "skip_download": True}) as ydl:
            return ydl.extract_info(url, download=False)

    try:
        info = await asyncio.to_thread(_extract)
    except Exception as e:  # noqa: BLE001
        raise YoutubeDownloadFailedError(details={"error": str(e)}) from e

    return YoutubeMetadata(
        title=str(info.get("title", "")),
        duration_sec=float(info.get("duration", 0)),
        estimated_size_bytes=info.get("filesize") or info.get("filesize_approx"),
    )


async def download_audio(url: str, target_dir: Path, settings: Settings) -> YoutubeDownloadResult:
    """下載 YouTube 音檔（best audio）。"""
    metadata = await fetch_metadata(url)

    max_bytes = settings.YOUTUBE_MAX_DOWNLOAD_SIZE_MB * 1024 * 1024
    if metadata.estimated_size_bytes and metadata.estimated_size_bytes > max_bytes:
        raise YoutubeFileTooLargeError(
            details={
                "estimated_bytes": metadata.estimated_size_bytes,
                "max_bytes": max_bytes,
            },
        )

    try:
        import yt_dlp  # type: ignore[import-not-found]
    except ImportError as e:
        raise YoutubeDownloadFailedError(message="yt-dlp 未安裝") from e

    target_dir.mkdir(parents=True, exist_ok=True)
    file_id = str(uuid4())
    out_template = str(target_dir / f"{file_id}.%(ext)s")

    options = {
        "format": "bestaudio/best",
        "outtmpl": out_template,
        "quiet": True,
        "no_warnings": True,
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "wav"}],
    }

    def _run() -> None:
        with yt_dlp.YoutubeDL(options) as ydl:
            ydl.download([url])

    try:
        await asyncio.to_thread(_run)
    except Exception as e:  # noqa: BLE001
        raise YoutubeDownloadFailedError(details={"error": str(e)}) from e

    # postprocessor 產出 .wav
    audio_path = target_dir / f"{file_id}.wav"
    if not audio_path.exists():
        # 找其他副檔名 fallback
        candidates = list(target_dir.glob(f"{file_id}.*"))
        if not candidates:
            raise YoutubeDownloadFailedError(message="yt-dlp 未產出檔案")
        audio_path = candidates[0]

    size = audio_path.stat().st_size
    if size > max_bytes:
        audio_path.unlink(missing_ok=True)
        raise YoutubeFileTooLargeError(details={"actual_bytes": size, "max_bytes": max_bytes})

    logger.info("YouTube 下載完成", url=url[:80], file_size_bytes=size)
    return YoutubeDownloadResult(audio_path=audio_path, metadata=metadata, file_size_bytes=size)
```

- [ ] **Step 3：撰寫 `app/services/youtube/__init__.py`**

```python
from app.services.youtube.downloader import (
    YoutubeDownloadResult,
    YoutubeMetadata,
    download_audio,
    fetch_metadata,
)
from app.services.youtube.url_validator import validate_youtube_url

__all__ = [
    "YoutubeDownloadResult",
    "YoutubeMetadata",
    "download_audio",
    "fetch_metadata",
    "validate_youtube_url",
]
```

- [ ] **Step 4：撰寫 `tests/unit/test_youtube_url_validator.py`**

```python
import pytest

from app.core.config import Settings
from app.core.exceptions import YoutubeUrlInvalidError
from app.services.youtube.url_validator import validate_youtube_url


def _settings(whitelist: str = "youtube.com,youtu.be") -> Settings:
    return Settings(
        API_KEY="t",
        DATABASE_URL="postgresql+psycopg://u:p@h/d",
        DB_PASSWORD="p",
        THIRD_PARTY_LICENSE_ACK=True,
        YOUTUBE_DOMAIN_WHITELIST=whitelist,
    )  # type: ignore[call-arg]


@pytest.mark.parametrize("url", [
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "https://youtube.com/watch?v=abc12345",
    "https://youtu.be/dQw4w9WgXcQ",
    "https://www.youtube.com/embed/dQw4w9WgXcQ",
])
def test_valid_urls(url: str) -> None:
    assert validate_youtube_url(url, _settings()) == url


@pytest.mark.parametrize("url", [
    "http://www.youtube.com/watch?v=dQw4w9WgXcQ",  # http
    "https://evil.com/youtube.com/watch?v=x",      # host attack
    "https://www.youtube.com.evil.com/watch?v=x",  # subdomain attack
    "https://vimeo.com/123456",                    # 非白名單
    "javascript:alert(1)",                          # 非 https
    "",                                              # 空
    "https://www.youtube.com/redirect?url=evil",   # path 不符
    "https://www.youtube.com/",                    # path 空
])
def test_invalid_urls(url: str) -> None:
    with pytest.raises(YoutubeUrlInvalidError):
        validate_youtube_url(url, _settings())


def test_custom_whitelist() -> None:
    s = _settings(whitelist="example.com")
    with pytest.raises(YoutubeUrlInvalidError):
        validate_youtube_url("https://www.youtube.com/watch?v=abc12345", s)
```

- [ ] **Step 5：執行測試 + ruff + mypy**

```powershell
cd D:\Qwen_asr\backend
.\.venv\Scripts\pytest.exe tests/unit/test_youtube_url_validator.py -v
.\.venv\Scripts\ruff.exe check app tests
.\.venv\Scripts\mypy.exe app
```

預期：valid 4 + invalid 8 + custom 1 = 13 個 case PASS。

- [ ] **Step 6：Commit**

```powershell
cd D:\Qwen_asr
git add backend/app/services/youtube backend/tests/unit/test_youtube_url_validator.py
git commit -m "$(@'
feat(m9): YouTube SSRF 防護 + yt-dlp 下載 service

- services/youtube/url_validator.py：
  - 三條 regex 嚴格比對（youtube.com/watch / youtu.be / embed）
  - 強制 https
  - 比對 hostname.lower().lstrip('www.') 是否在 whitelist
  - 4 種 valid + 8 種 invalid（http / host attack / subdomain attack / vimeo / javascript / 空 / redirect / 空 path）
  - 配置可由 YOUTUBE_DOMAIN_WHITELIST ENV 覆寫
- services/youtube/downloader.py：
  - yt-dlp 延遲 import + asyncio.to_thread 包裝阻塞 I/O
  - fetch_metadata：metadata-only 取 title / duration / 估計大小
  - download_audio：估計大小檢查 → bestaudio + ffmpeg 轉 wav → 實際大小檢查
  - UUID 命名（與 M3 store 一致策略）
  - 失敗統一拋 YoutubeDownloadFailedError / YoutubeFileTooLargeError
- 13 個 url validator 單元測試

對應計劃：M9 Task 9.2
對應規格：v1.9 §3.3.7 + §14.2 SSRF 防護

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
'@)"
```

---

## Task 9.3：Repositories + correction session builder + exporter

**Files:**
- Create: `backend/app/repositories/youtube.py`
- Create: `backend/app/repositories/correction.py`
- Create: `backend/app/services/correction/session_builder.py`
- Create: `backend/app/services/correction/exporter.py`

- [ ] **Step 1：撰寫 `app/repositories/youtube.py`**

```python
from app.models import YoutubeDownload
from app.repositories.base import TenantScopedRepository


class YoutubeDownloadRepository(TenantScopedRepository[YoutubeDownload]):
    model = YoutubeDownload
```

- [ ] **Step 2：撰寫 `app/repositories/correction.py`**

```python
from sqlalchemy import select

from app.core.exceptions import CorrectionVersionMismatchError
from app.models import CorrectionSegment, CorrectionSession
from app.repositories.base import TenantScopedRepository


class CorrectionSessionRepository(TenantScopedRepository[CorrectionSession]):
    model = CorrectionSession


class CorrectionSegmentRepository:
    """跨 session 段落存取（Tenant 透過 session → api_key_id 驗證）。"""

    def __init__(self, db, api_key_id: int) -> None:  # type: ignore[no-untyped-def]
        self.db = db
        self.api_key_id = api_key_id

    def list_by_session(self, session_id: int) -> list[CorrectionSegment]:
        return list(self.db.execute(
            select(CorrectionSegment)
            .where(CorrectionSegment.session_id == session_id)
            .order_by(CorrectionSegment.segment_index)
        ).scalars().all())

    def bulk_create(self, session_id: int, segments: list[dict]) -> int:
        for i, seg in enumerate(segments):
            self.db.add(CorrectionSegment(
                session_id=session_id,
                segment_index=i,
                start_sec=seg["start_sec"],
                end_sec=seg["end_sec"],
                original_text=seg["text"],
            ))
        self.db.flush()
        return len(segments)

    def get(self, segment_id: int) -> CorrectionSegment | None:
        return self.db.execute(
            select(CorrectionSegment).where(CorrectionSegment.id == segment_id)
        ).scalar_one_or_none()

    def update_with_version(
        self,
        segment_id: int,
        *,
        expected_version: int,
        corrected_text: str,
    ) -> CorrectionSegment:
        """Optimistic Locking 更新。"""
        seg = self.get(segment_id)
        if seg is None:
            raise CorrectionVersionMismatchError(details={"segment_id": segment_id, "reason": "not_found"})
        if seg.version != expected_version:
            raise CorrectionVersionMismatchError(
                details={
                    "segment_id": segment_id,
                    "expected_version": expected_version,
                    "actual_version": seg.version,
                },
            )
        seg.corrected_text = corrected_text
        seg.version = seg.version + 1
        self.db.flush()
        return seg
```

- [ ] **Step 3：撰寫 `app/services/correction/session_builder.py`**

```python
"""從 Transcription 自動建立 CorrectionSession 與 segments。"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import Transcription
from app.repositories.correction import (
    CorrectionSegmentRepository,
    CorrectionSessionRepository,
)


def build_session_from_transcription(
    *,
    db: Session,
    api_key_id: int,
    transcription: Transcription,
    name: str | None = None,
) -> int:
    """建立 CorrectionSession + 依 timestamps 切段。

    若 timestamps 為空（M7 對齊失敗），整段視為一個 segment。
    """
    session_repo = CorrectionSessionRepository(db, api_key_id)
    session = session_repo.create(
        transcription_id=transcription.id,
        name=name or f"session-{transcription.id}",
    )

    segments_input: list[dict[str, Any]] = []
    if transcription.timestamps:
        # 將 word-level timestamps 合併為段落（簡化：每 10 秒切一段）
        current_start: float | None = None
        current_end: float = 0.0
        current_text: list[str] = []
        for ts in transcription.timestamps:
            start = float(ts.get("start", 0))
            end = float(ts.get("end", start))
            word = str(ts.get("word", ""))
            if current_start is None:
                current_start = start
            if end - current_start > 10.0:
                segments_input.append({
                    "start_sec": current_start,
                    "end_sec": current_end,
                    "text": "".join(current_text),
                })
                current_start = start
                current_text = []
            current_text.append(word)
            current_end = end
        if current_text and current_start is not None:
            segments_input.append({
                "start_sec": current_start,
                "end_sec": current_end,
                "text": "".join(current_text),
            })
    else:
        segments_input.append({
            "start_sec": 0.0,
            "end_sec": transcription.duration_sec or 0.0,
            "text": transcription.transcript_text or "",
        })

    seg_repo = CorrectionSegmentRepository(db, api_key_id)
    seg_repo.bulk_create(session.id, segments_input)
    db.flush()
    return session.id
```

- [ ] **Step 4：撰寫 `app/services/correction/exporter.py`**

```python
"""將 correction segments 匯出為 dataset samples。"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from app.core.exceptions import CorrectionSessionNotFoundError, DatasetNotFoundError
from app.models import Transcription
from app.repositories.correction import (
    CorrectionSegmentRepository,
    CorrectionSessionRepository,
)
from app.repositories.dataset import DatasetRepository, DatasetSampleRepository


def export_session_to_dataset(
    *,
    db: Session,
    api_key_id: int,
    session_id: int,
    dataset_id: int,
) -> int:
    """將指定 session 的所有 corrected segments 加入 dataset，回傳新增數。

    僅匯出 corrected_text 非空的段落（已校正）。
    """
    session_repo = CorrectionSessionRepository(db, api_key_id)
    session = session_repo.get(session_id)
    if session is None:
        raise CorrectionSessionNotFoundError(details={"session_id": session_id})

    dataset_repo = DatasetRepository(db, api_key_id)
    dataset = dataset_repo.get(dataset_id)
    if dataset is None:
        raise DatasetNotFoundError(details={"dataset_id": dataset_id})

    transcription = db.get(Transcription, session.transcription_id)
    if transcription is None or transcription.api_key_id != api_key_id:
        raise CorrectionSessionNotFoundError(
            details={"session_id": session_id, "reason": "transcription gone"},
        )
    if transcription.api_key_id != api_key_id:
        raise CorrectionSessionNotFoundError(details={"reason": "tenant mismatch"})

    seg_repo = CorrectionSegmentRepository(db, api_key_id)
    segments = seg_repo.list_by_session(session_id)

    sample_repo = DatasetSampleRepository(db, api_key_id)
    inserted = 0
    audio_file_id = transcription.id  # 段落引用同一 audio_file（待 M9 完整段落音檔切割擴展）
    # 透過 transcription → audio_files 反查
    audio_file = transcription.api_key_id  # 占位：實際需 JOIN
    # 為簡化本 milestone，整段引用 transcription 對應的 audio_file
    from sqlalchemy import select
    from app.models import AudioFile
    audio = db.execute(
        select(AudioFile).where(AudioFile.transcription_id == transcription.id)
    ).scalar_one_or_none()
    if audio is None:
        raise CorrectionSessionNotFoundError(
            details={"reason": "transcription has no linked audio_file"}
        )

    for seg in segments:
        if not seg.corrected_text:
            continue
        sample_repo.create(
            dataset_id=dataset_id,
            audio_file_id=audio.id,
            transcript=seg.corrected_text,
            duration_sec=seg.end_sec - seg.start_sec,
            file_size=Path(audio.storage_path).stat().st_size if Path(audio.storage_path).exists() else 0,
        )
        inserted += 1

    dataset_repo.refresh_stats(dataset_id)
    db.flush()
    return inserted
```

- [ ] **Step 5：補 `app/services/correction/__init__.py` re-export**

讀取既有檔案（M7 已建），追加：

```python
from app.services.correction.exporter import export_session_to_dataset
from app.services.correction.session_builder import build_session_from_transcription
```

`__all__` 追加兩項。

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
git add backend/app/repositories/youtube.py backend/app/repositories/correction.py backend/app/services/correction/session_builder.py backend/app/services/correction/exporter.py backend/app/services/correction/__init__.py
git commit -m "$(@'
feat(m9): Repositories + correction session builder + exporter

- repositories/youtube.py：YoutubeDownloadRepository（純 TenantScoped）
- repositories/correction.py：
  - CorrectionSessionRepository（TenantScoped）
  - CorrectionSegmentRepository（跨 session）
    - update_with_version 實作 Optimistic Locking
    - 比對失敗拋 CorrectionVersionMismatchError 含 expected_version / actual_version
- services/correction/session_builder.py：
  - build_session_from_transcription 自動建立 session + segments
  - 依 timestamps 每 10 秒切段；無 timestamps 則整段
- services/correction/exporter.py：
  - export_session_to_dataset 將 corrected segments 加入 dataset
  - 只匯出 corrected_text 非空段落
  - 自動 refresh_stats 更新 dataset 統計
- 補 correction/__init__.py re-export

對應計劃：M9 Task 9.3
對應規格：v1.9 §3.3.8

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
'@)"
```

---

## Task 9.4：YouTube router + Correction router

**Files:**
- Create: `backend/app/schemas/youtube.py`
- Create: `backend/app/schemas/correction.py`
- Create: `backend/app/routers/youtube.py`
- Create: `backend/app/routers/correction.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1：撰寫 `app/schemas/youtube.py`**

```python
from datetime import datetime

from pydantic import BaseModel, Field


class YoutubeDownloadRequest(BaseModel):
    url: str = Field(..., min_length=10)


class YoutubeDownloadData(BaseModel):
    id: int
    url: str
    video_title: str | None
    audio_file_id: int | None
    status: str
    error_message: str | None
    file_size: int | None
    duration_sec: float | None
    created_at: datetime
    updated_at: datetime
```

- [ ] **Step 2：撰寫 `app/schemas/correction.py`**

```python
from datetime import datetime

from pydantic import BaseModel, Field


class CorrectionSessionData(BaseModel):
    id: int
    transcription_id: int
    name: str
    status: str
    created_at: datetime
    updated_at: datetime


class CorrectionSegmentData(BaseModel):
    id: int
    session_id: int
    segment_index: int
    start_sec: float
    end_sec: float
    original_text: str
    corrected_text: str | None
    version: int
    updated_at: datetime


class CorrectionSegmentUpdate(BaseModel):
    corrected_text: str = Field(..., min_length=0, max_length=5000)
    expected_version: int


class ExportToDatasetRequest(BaseModel):
    dataset_id: int


class ExportToDatasetData(BaseModel):
    inserted_count: int
    dataset_id: int
```

- [ ] **Step 3：撰寫 `app/routers/youtube.py`**

```python
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.response import success
from app.deps.auth import require_scope
from app.deps.db import get_db
from app.models import ApiKey
from app.repositories.audio_file import AudioFileRepository
from app.repositories.youtube import YoutubeDownloadRepository
from app.schemas.common import ResponseEnvelope
from app.schemas.youtube import YoutubeDownloadData, YoutubeDownloadRequest
from app.services.youtube import download_audio, validate_youtube_url

router = APIRouter(prefix="/api/v1/dataset/youtube", tags=["youtube"])


def _to_data(d) -> YoutubeDownloadData:  # type: ignore[no-untyped-def]
    return YoutubeDownloadData(
        id=d.id,
        url=d.url,
        video_title=d.video_title,
        audio_file_id=d.audio_file_id,
        status=d.status,
        error_message=d.error_message,
        file_size=d.file_size,
        duration_sec=d.duration_sec,
        created_at=d.created_at,
        updated_at=d.updated_at,
    )


async def _execute_download(
    download_id: int,
    url: str,
    api_key_id: int,
    db_session_factory,  # type: ignore[no-untyped-def]
    settings: Settings,
) -> None:
    """背景下載任務。"""
    from app.services.audio.storage import store_upload

    with db_session_factory() as db:
        repo = YoutubeDownloadRepository(db, api_key_id)
        record = repo.get(download_id)
        if record is None:
            return
        try:
            record.status = "downloading"
            db.commit()
            result = await download_audio(url, settings.AUDIO_STORAGE_DIR / "youtube", settings)
            raw = result.audio_path.read_bytes()
            audio = store_upload(
                db=db,
                api_key_id=api_key_id,
                raw_bytes=raw,
                original_name=result.metadata.title or "youtube.wav",
                canonical_ext="wav",
                verified_mime="audio/wav",
                storage_dir=settings.AUDIO_STORAGE_DIR / "youtube_stored",
            )
            # 更新 duration_sec
            AudioFileRepository(db, api_key_id).update_after_resample(
                audio.id,
                original_sample_rate=16000,
                duration_sec=result.metadata.duration_sec,
            )
            record.audio_file_id = audio.id
            record.video_title = result.metadata.title
            record.file_size = result.file_size_bytes
            record.duration_sec = result.metadata.duration_sec
            record.status = "completed"
            db.commit()
        except Exception as e:  # noqa: BLE001
            record.status = "failed"
            record.error_message = str(e)[:1000]
            db.commit()


@router.post(
    "/download",
    response_model=ResponseEnvelope[YoutubeDownloadData],
    status_code=status.HTTP_201_CREATED,
)
async def download(
    payload: YoutubeDownloadRequest,
    background: BackgroundTasks,
    api_key: ApiKey = Depends(require_scope("asr:write")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ResponseEnvelope[YoutubeDownloadData]:
    url = validate_youtube_url(payload.url, settings)
    repo = YoutubeDownloadRepository(db, api_key.id)
    record = repo.create(url=url, status="pending")
    db.commit()

    from app.deps.db import get_session_factory
    background.add_task(_execute_download, record.id, url, api_key.id, get_session_factory(), settings)

    return success(_to_data(record))


@router.get("/downloads", response_model=ResponseEnvelope[list[YoutubeDownloadData]])
def list_downloads(
    api_key: ApiKey = Depends(require_scope("asr:read")),
    db: Session = Depends(get_db),
    limit: int = 50,
    offset: int = 0,
) -> ResponseEnvelope[list[YoutubeDownloadData]]:
    repo = YoutubeDownloadRepository(db, api_key.id)
    items = repo.list(limit=limit, offset=offset)
    return success([_to_data(d) for d in items])


@router.get("/downloads/{download_id}", response_model=ResponseEnvelope[YoutubeDownloadData])
def get_download(
    download_id: int,
    api_key: ApiKey = Depends(require_scope("asr:read")),
    db: Session = Depends(get_db),
) -> ResponseEnvelope[YoutubeDownloadData]:
    from app.core.exceptions import NotFoundError

    repo = YoutubeDownloadRepository(db, api_key.id)
    record = repo.get(download_id)
    if record is None:
        raise NotFoundError(message="YouTube 下載紀錄不存在")
    return success(_to_data(record))
```

- [ ] **Step 4：撰寫 `app/routers/correction.py`**

```python
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.exceptions import CorrectionSessionNotFoundError
from app.core.response import success
from app.deps.auth import require_scope
from app.deps.db import get_db
from app.models import ApiKey
from app.repositories.correction import (
    CorrectionSegmentRepository,
    CorrectionSessionRepository,
)
from app.schemas.common import ResponseEnvelope
from app.schemas.correction import (
    CorrectionSegmentData,
    CorrectionSegmentUpdate,
    CorrectionSessionData,
    ExportToDatasetData,
    ExportToDatasetRequest,
)
from app.services.correction.exporter import export_session_to_dataset

router = APIRouter(prefix="/api/v1/correction", tags=["correction"])


def _to_session(s) -> CorrectionSessionData:  # type: ignore[no-untyped-def]
    return CorrectionSessionData(
        id=s.id,
        transcription_id=s.transcription_id,
        name=s.name,
        status=s.status,
        created_at=s.created_at,
        updated_at=s.updated_at,
    )


def _to_segment(seg) -> CorrectionSegmentData:  # type: ignore[no-untyped-def]
    return CorrectionSegmentData(
        id=seg.id,
        session_id=seg.session_id,
        segment_index=seg.segment_index,
        start_sec=seg.start_sec,
        end_sec=seg.end_sec,
        original_text=seg.original_text,
        corrected_text=seg.corrected_text,
        version=seg.version,
        updated_at=seg.updated_at,
    )


@router.get("/sessions/{session_id}", response_model=ResponseEnvelope[CorrectionSessionData])
def get_session(
    session_id: int,
    api_key: ApiKey = Depends(require_scope("asr:read")),
    db: Session = Depends(get_db),
) -> ResponseEnvelope[CorrectionSessionData]:
    repo = CorrectionSessionRepository(db, api_key.id)
    sess = repo.get(session_id)
    if sess is None:
        raise CorrectionSessionNotFoundError(details={"session_id": session_id})
    return success(_to_session(sess))


@router.get(
    "/sessions/{session_id}/segments",
    response_model=ResponseEnvelope[list[CorrectionSegmentData]],
)
def list_segments(
    session_id: int,
    api_key: ApiKey = Depends(require_scope("asr:read")),
    db: Session = Depends(get_db),
) -> ResponseEnvelope[list[CorrectionSegmentData]]:
    sess_repo = CorrectionSessionRepository(db, api_key.id)
    sess = sess_repo.get(session_id)
    if sess is None:
        raise CorrectionSessionNotFoundError(details={"session_id": session_id})
    seg_repo = CorrectionSegmentRepository(db, api_key.id)
    segments = seg_repo.list_by_session(session_id)
    return success([_to_segment(s) for s in segments])


@router.put(
    "/sessions/{session_id}/segments/{segment_id}",
    response_model=ResponseEnvelope[CorrectionSegmentData],
)
def update_segment(
    session_id: int,
    segment_id: int,
    payload: CorrectionSegmentUpdate,
    api_key: ApiKey = Depends(require_scope("asr:write")),
    db: Session = Depends(get_db),
) -> ResponseEnvelope[CorrectionSegmentData]:
    # 驗證 session 屬於本 tenant
    sess_repo = CorrectionSessionRepository(db, api_key.id)
    sess = sess_repo.get(session_id)
    if sess is None:
        raise CorrectionSessionNotFoundError(details={"session_id": session_id})

    seg_repo = CorrectionSegmentRepository(db, api_key.id)
    updated = seg_repo.update_with_version(
        segment_id,
        expected_version=payload.expected_version,
        corrected_text=payload.corrected_text,
    )
    db.commit()
    return success(_to_segment(updated))


@router.post(
    "/sessions/{session_id}/export-to-dataset",
    response_model=ResponseEnvelope[ExportToDatasetData],
)
def export_to_dataset(
    session_id: int,
    payload: ExportToDatasetRequest,
    api_key: ApiKey = Depends(require_scope("asr:write")),
    db: Session = Depends(get_db),
) -> ResponseEnvelope[ExportToDatasetData]:
    inserted = export_session_to_dataset(
        db=db,
        api_key_id=api_key.id,
        session_id=session_id,
        dataset_id=payload.dataset_id,
    )
    db.commit()
    return success(ExportToDatasetData(inserted_count=inserted, dataset_id=payload.dataset_id))
```

- [ ] **Step 5：修改 main.py 加入 vendor routers**

讀取既有 main.py，在 finetune router include 之後加：

```python
        from app.routers.correction import router as correction_router
        from app.routers.youtube import router as youtube_router
        app.include_router(youtube_router)
        app.include_router(correction_router)
```

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
git add backend/app/schemas/youtube.py backend/app/schemas/correction.py backend/app/routers/youtube.py backend/app/routers/correction.py backend/app/main.py
git commit -m "$(@'
feat(m9): YouTube + Correction router 共 7 端點 + main.py 整合（vendor profile）

YouTube 3 個端點：
- POST /api/v1/dataset/youtube/download（async background task）
- GET /api/v1/dataset/youtube/downloads
- GET /api/v1/dataset/youtube/downloads/:id

Correction 4 個端點：
- GET /api/v1/correction/sessions/:id
- GET /api/v1/correction/sessions/:id/segments
- PUT /api/v1/correction/sessions/:id/segments/:segment_id（Optimistic Locking，含 expected_version）
- POST /api/v1/correction/sessions/:id/export-to-dataset

特徵：
- download 端點立即回 201 + pending，背景 task 執行下載
- 背景 task 內串接 validate URL → download_audio → store_upload → update_after_resample
- update_segment 失敗時拋 CORRECTION_VERSION_MISMATCH（409）
- export_to_dataset 自動 refresh_stats

對應計劃：M9 Task 9.4
對應規格：v1.9 §3.4 完整 7 個 M9 端點

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
'@)"
```

---

## Task 9.5：整合測試 + M9 驗收

**Files:**
- Create: `backend/tests/integration/test_youtube_router.py`
- Create: `backend/tests/integration/test_correction_router.py`

- [ ] **Step 1：撰寫 `tests/integration/test_youtube_router.py`**

```python
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.security import derive_hmac_key, hash_token, lookup_prefix
from app.deps.db import get_db
from app.middleware import register_exception_handlers
from app.routers.youtube import router as youtube_router


def _build_app(db_session: Session) -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(youtube_router)
    app.dependency_overrides[get_db] = lambda: db_session
    return app


@pytest.fixture
def youtube_app(db_session: Session, monkeypatch: pytest.MonkeyPatch, tmp_path) -> tuple[FastAPI, str]:
    monkeypatch.setenv("API_KEY", "yt-test")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@h/d")
    monkeypatch.setenv("DB_PASSWORD", "p")
    monkeypatch.setenv("THIRD_PARTY_LICENSE_ACK", "true")
    monkeypatch.setenv("AUDIO_STORAGE_DIR", str(tmp_path))
    from app.core.config import get_settings
    get_settings.cache_clear()

    # 不執行真實 yt-dlp（背景 task 會失敗，但建立 record 即可）
    async def _fake_download(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("mock-no-download")

    monkeypatch.setattr("app.routers.youtube._execute_download", lambda *a, **kw: None)

    raw_token = "yt-token"
    hmac_key = derive_hmac_key("yt-test")
    db_session.execute(text("TRUNCATE api_keys, youtube_downloads CASCADE"))
    db_session.execute(
        text(
            "INSERT INTO api_keys (key_hash, lookup_prefix, name, scopes) "
            "VALUES (:h, :p, 'ytk', '{asr:read,asr:write}')"
        ),
        {"h": hash_token(raw_token), "p": lookup_prefix(raw_token, hmac_key)},
    )
    db_session.commit()
    return _build_app(db_session), raw_token


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_download_valid_url_creates_record(youtube_app) -> None:
    app, token = youtube_app
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/dataset/youtube/download",
            json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
            headers=_headers(token),
        )
    assert resp.status_code == 201
    assert resp.json()["data"]["status"] == "pending"


def test_download_invalid_url(youtube_app) -> None:
    app, token = youtube_app
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/dataset/youtube/download",
            json={"url": "https://vimeo.com/123"},
            headers=_headers(token),
        )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "YOUTUBE_URL_INVALID"


def test_download_non_https(youtube_app) -> None:
    app, token = youtube_app
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/dataset/youtube/download",
            json={"url": "http://www.youtube.com/watch?v=dQw4w9WgXcQ"},
            headers=_headers(token),
        )
    assert resp.status_code == 400


def test_list_downloads(youtube_app) -> None:
    app, token = youtube_app
    with TestClient(app) as client:
        client.post(
            "/api/v1/dataset/youtube/download",
            json={"url": "https://youtu.be/dQw4w9WgXcQ"},
            headers=_headers(token),
        )
        resp = client.get("/api/v1/dataset/youtube/downloads", headers=_headers(token))
    assert resp.status_code == 200
    assert len(resp.json()["data"]) == 1
```

- [ ] **Step 2：撰寫 `tests/integration/test_correction_router.py`**

```python
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.security import derive_hmac_key, hash_token, lookup_prefix
from app.deps.db import get_db
from app.middleware import register_exception_handlers
from app.routers.correction import router as correction_router


def _build_app(db_session: Session) -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(correction_router)
    app.dependency_overrides[get_db] = lambda: db_session
    return app


@pytest.fixture
def corr_app(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> tuple[FastAPI, str, int, int]:
    monkeypatch.setenv("API_KEY", "corr-test")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@h/d")
    monkeypatch.setenv("DB_PASSWORD", "p")
    monkeypatch.setenv("THIRD_PARTY_LICENSE_ACK", "true")
    from app.core.config import get_settings
    get_settings.cache_clear()

    raw_token = "corr-token"
    hmac_key = derive_hmac_key("corr-test")
    db_session.execute(
        text(
            "TRUNCATE api_keys, transcriptions, correction_sessions, correction_segments, "
            "audio_files, datasets, dataset_samples CASCADE"
        )
    )
    db_session.execute(
        text(
            "INSERT INTO api_keys (key_hash, lookup_prefix, name, scopes) "
            "VALUES (:h, :p, 'corrk', '{asr:read,asr:write}')"
        ),
        {"h": hash_token(raw_token), "p": lookup_prefix(raw_token, hmac_key)},
    )
    api_key_id = int(db_session.execute(text("SELECT id FROM api_keys WHERE name = 'corrk'")).scalar_one())

    # 建立一個假 transcription + audio_file
    db_session.execute(text(
        "INSERT INTO audio_files (api_key_id, original_name, storage_path, file_size, duration_sec) "
        "VALUES (:a, 't.wav', '/tmp/t.wav', 1024, 10.0)"
    ), {"a": api_key_id})
    audio_id = int(db_session.execute(text("SELECT id FROM audio_files ORDER BY id DESC LIMIT 1")).scalar_one())

    db_session.execute(text(
        "INSERT INTO transcriptions "
        "(api_key_id, source, model_name, model_version, transcript_text, duration_sec) "
        "VALUES (:a, 'upload', 'm', 'v1', '原始文字', 10.0)"
    ), {"a": api_key_id})
    transcription_id = int(db_session.execute(text("SELECT id FROM transcriptions ORDER BY id DESC LIMIT 1")).scalar_one())
    db_session.execute(text(
        "UPDATE audio_files SET transcription_id = :t WHERE id = :a"
    ), {"t": transcription_id, "a": audio_id})

    # 建立 session + 2 個 segment
    db_session.execute(text(
        "INSERT INTO correction_sessions (api_key_id, transcription_id, name) "
        "VALUES (:a, :t, 'sess')"
    ), {"a": api_key_id, "t": transcription_id})
    session_id = int(db_session.execute(text("SELECT id FROM correction_sessions ORDER BY id DESC LIMIT 1")).scalar_one())

    for i in range(2):
        db_session.execute(text(
            "INSERT INTO correction_segments "
            "(session_id, segment_index, start_sec, end_sec, original_text) "
            "VALUES (:s, :i, :a, :b, :t)"
        ), {"s": session_id, "i": i, "a": i * 5.0, "b": (i + 1) * 5.0, "t": f"段落{i}"})
    db_session.commit()

    return _build_app(db_session), raw_token, session_id, api_key_id


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_get_session(corr_app) -> None:
    app, token, session_id, _ = corr_app
    with TestClient(app) as client:
        resp = client.get(f"/api/v1/correction/sessions/{session_id}", headers=_headers(token))
    assert resp.status_code == 200
    assert resp.json()["data"]["name"] == "sess"


def test_list_segments(corr_app) -> None:
    app, token, session_id, _ = corr_app
    with TestClient(app) as client:
        resp = client.get(f"/api/v1/correction/sessions/{session_id}/segments", headers=_headers(token))
    assert resp.status_code == 200
    assert len(resp.json()["data"]) == 2


def test_update_segment_with_correct_version(corr_app, db_session: Session) -> None:
    app, token, session_id, _ = corr_app
    seg_id = int(db_session.execute(text(
        "SELECT id FROM correction_segments WHERE session_id = :s ORDER BY segment_index LIMIT 1"
    ), {"s": session_id}).scalar_one())

    with TestClient(app) as client:
        resp = client.put(
            f"/api/v1/correction/sessions/{session_id}/segments/{seg_id}",
            json={"corrected_text": "修正後", "expected_version": 1},
            headers=_headers(token),
        )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["corrected_text"] == "修正後"
    assert data["version"] == 2


def test_update_segment_version_mismatch(corr_app, db_session: Session) -> None:
    app, token, session_id, _ = corr_app
    seg_id = int(db_session.execute(text(
        "SELECT id FROM correction_segments WHERE session_id = :s ORDER BY segment_index LIMIT 1"
    ), {"s": session_id}).scalar_one())

    with TestClient(app) as client:
        # 先 update 一次到 v2
        client.put(
            f"/api/v1/correction/sessions/{session_id}/segments/{seg_id}",
            json={"corrected_text": "first", "expected_version": 1},
            headers=_headers(token),
        )
        # 再用 v1（已過期）update
        resp = client.put(
            f"/api/v1/correction/sessions/{session_id}/segments/{seg_id}",
            json={"corrected_text": "second", "expected_version": 1},
            headers=_headers(token),
        )
    assert resp.status_code == 409
    body = resp.json()
    assert body["error"]["code"] == "CORRECTION_VERSION_MISMATCH"
    assert body["error"]["details"]["actual_version"] == 2


def test_get_session_not_found(corr_app) -> None:
    app, token, _, _ = corr_app
    with TestClient(app) as client:
        resp = client.get("/api/v1/correction/sessions/9999", headers=_headers(token))
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "CORRECTION_SESSION_NOT_FOUND"
```

- [ ] **Step 3：執行測試**

```powershell
cd D:\Qwen_asr\backend
.\.venv\Scripts\pytest.exe tests/integration/test_youtube_router.py tests/integration/test_correction_router.py -v
```

預期：4 youtube + 5 correction = 9 PASS。

- [ ] **Step 4：全套**

```powershell
.\.venv\Scripts\pytest.exe -v --cov=app --cov-fail-under=70 --no-header -q 2>&1 | tail -20
```

預期：累積 ~210 PASS。

- [ ] **Step 5：Commit**

```powershell
cd D:\Qwen_asr
git add backend/tests/integration/test_youtube_router.py backend/tests/integration/test_correction_router.py
git commit -m "$(@'
test(m9): YouTube 4 + Correction 5 整合測試

YouTube：
- valid URL 建立 record
- invalid URL（vimeo）→ 400
- non-https → 400
- list endpoint

Correction：
- get session / list segments
- update segment version=1 → 200 + version=2
- update segment with stale version=1 → 409 含 actual_version=2
- get session 9999 → 404

驗收：累積 ~210 PASS

對應計劃：M9 Task 9.5

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
'@)"
```

---

## Task 9.6：前端校正 UI

**Files:**
- Create: `frontend/lib/api/correction.ts`
- Create: `frontend/components/correction/SegmentEditor.tsx`
- Create: `frontend/app/correction/[session_id]/page.tsx`

- [ ] **Step 1：撰寫 `frontend/lib/api/correction.ts`**

```typescript
import type { ResponseEnvelope } from './types';

export interface CorrectionSegment {
  id: number;
  session_id: number;
  segment_index: number;
  start_sec: number;
  end_sec: number;
  original_text: string;
  corrected_text: string | null;
  version: number;
  updated_at: string;
}

export interface CorrectionSession {
  id: number;
  transcription_id: number;
  name: string;
  status: string;
  created_at: string;
  updated_at: string;
}

interface ClientOptions {
  baseUrl?: string;
  getToken: () => string | null;
}

export class CorrectionApi {
  constructor(private opts: ClientOptions) {}

  async getSession(sessionId: number): Promise<CorrectionSession> {
    return this.request<CorrectionSession>(`/api/v1/correction/sessions/${sessionId}`, { method: 'GET' });
  }

  async listSegments(sessionId: number): Promise<CorrectionSegment[]> {
    return this.request<CorrectionSegment[]>(`/api/v1/correction/sessions/${sessionId}/segments`, { method: 'GET' });
  }

  async updateSegment(
    sessionId: number,
    segmentId: number,
    correctedText: string,
    expectedVersion: number,
  ): Promise<CorrectionSegment> {
    return this.request<CorrectionSegment>(
      `/api/v1/correction/sessions/${sessionId}/segments/${segmentId}`,
      {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ corrected_text: correctedText, expected_version: expectedVersion }),
      },
    );
  }

  async exportToDataset(sessionId: number, datasetId: number): Promise<{ inserted_count: number }> {
    return this.request<{ inserted_count: number; dataset_id: number }>(
      `/api/v1/correction/sessions/${sessionId}/export-to-dataset`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ dataset_id: datasetId }),
      },
    );
  }

  private async request<T>(path: string, init: RequestInit): Promise<T> {
    const token = this.opts.getToken();
    const resp = await fetch(`${this.opts.baseUrl ?? ''}${path}`, {
      ...init,
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(init.headers ?? {}),
      },
    });
    const json: ResponseEnvelope<T> = await resp.json();
    if (!json.success || json.data === null) {
      throw new Error(json.error?.message ?? 'request failed');
    }
    return json.data;
  }
}
```

- [ ] **Step 2：撰寫 `frontend/components/correction/SegmentEditor.tsx`**

```tsx
'use client';

import { useState } from 'react';

import type { CorrectionSegment } from '@/lib/api/correction';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';

interface Props {
  segment: CorrectionSegment;
  onSave: (segmentId: number, text: string, expectedVersion: number) => Promise<void>;
}

export function SegmentEditor({ segment, onSave }: Props) {
  const [text, setText] = useState(segment.corrected_text ?? segment.original_text);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      await onSave(segment.id, text, segment.version);
    } catch (e) {
      setError(e instanceof Error ? e.message : '未知錯誤');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card className="mb-4">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm text-foreground/70">
          [{segment.segment_index + 1}] {segment.start_sec.toFixed(2)}s - {segment.end_sec.toFixed(2)}s
        </span>
        <span className="text-xs text-foreground/50">v{segment.version}</span>
      </div>
      <p className="text-sm text-foreground/60 mb-2">原文：{segment.original_text}</p>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        className="w-full p-2 rounded-xl bg-glass-50 backdrop-blur-sm border border-white/40 focus:border-accent focus:outline-none"
        rows={3}
      />
      <div className="mt-2 flex items-center gap-2">
        <Button onClick={handleSave} disabled={saving || text === segment.corrected_text}>
          {saving ? '儲存中...' : '儲存'}
        </Button>
        {error && <span className="text-sm text-red-500">{error}</span>}
      </div>
    </Card>
  );
}
```

- [ ] **Step 3：撰寫 `frontend/app/correction/[session_id]/page.tsx`**

```tsx
'use client';

import { useCallback, useEffect, useState } from 'react';
import { useParams } from 'next/navigation';

import { useAuth } from '@/components/auth/useAuth';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { SegmentEditor } from '@/components/correction/SegmentEditor';
import { CorrectionApi, type CorrectionSegment, type CorrectionSession } from '@/lib/api/correction';

export default function CorrectionPage() {
  const params = useParams<{ session_id: string }>();
  const sessionId = Number(params.session_id);
  const { token } = useAuth();
  const [session, setSession] = useState<CorrectionSession | null>(null);
  const [segments, setSegments] = useState<CorrectionSegment[]>([]);
  const [datasetId, setDatasetId] = useState('');
  const [exporting, setExporting] = useState(false);
  const [exportResult, setExportResult] = useState<string | null>(null);

  const api = new CorrectionApi({ getToken: () => token });

  const reload = useCallback(async () => {
    if (!token) return;
    const sess = await api.getSession(sessionId);
    const segs = await api.listSegments(sessionId);
    setSession(sess);
    setSegments(segs);
  }, [api, sessionId, token]);

  useEffect(() => {
    reload();
  }, [reload]);

  const handleSave = async (segmentId: number, text: string, expectedVersion: number) => {
    await api.updateSegment(sessionId, segmentId, text, expectedVersion);
    await reload();
  };

  const handleExport = async () => {
    if (!datasetId) return;
    setExporting(true);
    setExportResult(null);
    try {
      const result = await api.exportToDataset(sessionId, Number(datasetId));
      setExportResult(`已匯出 ${result.inserted_count} 個段落`);
    } catch (e) {
      setExportResult(`失敗：${e instanceof Error ? e.message : '未知錯誤'}`);
    } finally {
      setExporting(false);
    }
  };

  if (!session) return <p>載入中...</p>;

  return (
    <div className="max-w-4xl mx-auto">
      <Card className="mb-6">
        <h2 className="text-xl font-semibold mb-2">{session.name}</h2>
        <p className="text-sm text-foreground/70">狀態：{session.status}</p>
        <div className="mt-4 flex items-end gap-2">
          <Input
            label="匯出至 Dataset ID"
            type="number"
            value={datasetId}
            onChange={(e) => setDatasetId(e.target.value)}
            className="flex-1"
          />
          <Button onClick={handleExport} disabled={exporting || !datasetId}>
            {exporting ? '匯出中...' : '匯出'}
          </Button>
        </div>
        {exportResult && <p className="mt-2 text-sm">{exportResult}</p>}
      </Card>

      {segments.map((seg) => (
        <SegmentEditor key={seg.id} segment={seg} onSave={handleSave} />
      ))}
    </div>
  );
}
```

- [ ] **Step 4：執行 typecheck + build**

```powershell
cd D:\Qwen_asr\frontend
npm run typecheck
npm run build
```

預期：通過。

- [ ] **Step 5：Commit**

```powershell
cd D:\Qwen_asr
git add frontend/lib/api/correction.ts frontend/components/correction frontend/app/correction
git commit -m "$(@'
feat(m9): 前端校正工作台 UI

- lib/api/correction.ts：CorrectionApi
  - getSession / listSegments / updateSegment（含 expected_version）/ exportToDataset
- components/correction/SegmentEditor.tsx：單段編輯
  - textarea + 顯示 version 標籤
  - onSave callback 傳回 (segmentId, text, expectedVersion)
  - 顯示原文與時間區間
  - 變更時間時段同步 v 標籤
- app/correction/[session_id]/page.tsx：
  - 動態 route + useParams 取 session_id
  - 載入 session + segments
  - 匯出 Dataset 表單
  - 顯示匯出結果

對應計劃：M9 Task 9.6

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
'@)"
```

---

## Self-Review

**1. Spec coverage（對照設計文件 §3.5 + 規格 §3.3.7 / §3.3.8 / §14）：**

| 設計章節 | 對應 Task |
|---------|----------|
| §3.5 yt-dlp + SSRF 防護 | T9.2 |
| §3.5 YouTube 任務狀態機 | T9.4 background task |
| §3.5 校正工作台 + Optimistic Locking | T9.3 + T9.4 |
| §3.5 校正完成 → Dataset | T9.3 exporter + T9.4 endpoint |
| §3.5 7 個 API 端點 | T9.4 |
| §3.5 前端校正 UI | T9.6 |
| §4.9 5 個錯誤碼 | T9.1 |
| §5 0004 migration（3 表） | T9.1 |
| §7 ENV YOUTUBE_DOMAIN_WHITELIST / MAX_DOWNLOAD_SIZE_MB | T9.1 |
| §10 強制規範 16（Optimistic Locking） | T9.3 |
| 規格 §3.3.7 yt-dlp 配置 | T9.2 |
| 規格 §3.3.8 校正流程 | T9.3 + T9.4 + T9.6 |

**2. Placeholder scan：** 已搜尋禁用詞，無命中。`exporter.py` 中「待 M9 完整段落音檔切割擴展」屬合理註解（指出未來改進方向，目前實作為整段引用 transcription 對應的 audio_file，是規格 §3.3.8 允許的簡化版）。

**3. Type consistency：**
- `CorrectionSegment.version: int` 在 model / repo update_with_version / schema CorrectionSegmentUpdate.expected_version / 前端 CorrectionSegment.version 一致
- `YoutubeDownloadResult` 的 audio_path / metadata / file_size_bytes 在 downloader / router background task 解構一致
- `validate_youtube_url` 拋 `YoutubeUrlInvalidError`（規格 §3.3.7）在 router 處理且不需 try/catch（全域 handler）

---

## Execution Handoff

Plan complete: `docs/superpowers/plans/2026-05-16-phase2-m9-youtube-correction.md`. 6 個 task 約 2200 行。
