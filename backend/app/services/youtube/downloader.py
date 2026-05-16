"""yt-dlp 包裝（規格 §3.3.7）。

關鍵設計：
- yt-dlp 延遲 import（與其他 audio extras 一致）
- 先 metadata 檢查（skip_download）
- 下載完成後重命名為 UUID（M3 既有 store_upload 模式）
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any
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
        import yt_dlp  # type: ignore[import-untyped]
    except ImportError as e:
        raise YoutubeDownloadFailedError(message="yt-dlp 未安裝") from e

    def _extract() -> dict[str, Any]:
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "skip_download": True}) as ydl:
            return ydl.extract_info(url, download=False)  # type: ignore[no-any-return]

    try:
        info = await asyncio.to_thread(_extract)
    except Exception as e:
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
        import yt_dlp
    except ImportError as e:
        raise YoutubeDownloadFailedError(message="yt-dlp 未安裝") from e

    target_dir.mkdir(parents=True, exist_ok=True)  # noqa: ASYNC240
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
    except Exception as e:
        raise YoutubeDownloadFailedError(details={"error": str(e)}) from e

    audio_path = target_dir / f"{file_id}.wav"
    if not audio_path.exists():
        candidates = list(target_dir.glob(f"{file_id}.*"))  # noqa: ASYNC240
        if not candidates:
            raise YoutubeDownloadFailedError(message="yt-dlp 未產出檔案")
        audio_path = candidates[0]

    size = audio_path.stat().st_size
    if size > max_bytes:
        audio_path.unlink(missing_ok=True)
        raise YoutubeFileTooLargeError(details={"actual_bytes": size, "max_bytes": max_bytes})

    logger.info("YouTube 下載完成", url=url[:80], file_size_bytes=size)
    return YoutubeDownloadResult(audio_path=audio_path, metadata=metadata, file_size_bytes=size)
