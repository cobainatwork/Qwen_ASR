"""Fine-tune file lock 機制（M8 完整實作，M7 先建以支援推理降級判斷）。

規格 §18.2：Fine-tune 進行時推理服務必須降級。
"""

from __future__ import annotations

import os
from pathlib import Path

import structlog

from app.core.config import Settings

logger = structlog.get_logger(__name__)


def get_lock_path(settings: Settings) -> Path:
    return Path(getattr(settings, "FINETUNE_LOCK_PATH", "/data/finetune.lock"))


def is_finetune_active(settings: Settings) -> bool:
    return get_lock_path(settings).exists()


def acquire_lock(settings: Settings) -> None:
    path = get_lock_path(settings)
    if path.exists():
        raise RuntimeError(f"Finetune lock already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(os.getpid()))
    logger.info("finetune lock acquired", path=str(path), pid=os.getpid())


def release_lock(settings: Settings) -> None:
    path = get_lock_path(settings)
    path.unlink(missing_ok=True)
    logger.info("finetune lock released", path=str(path))
