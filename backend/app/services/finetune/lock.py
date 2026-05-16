"""Fine-tune file lock 機制。

規格 §18.2：Fine-tune 進行時推理服務必須降級。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

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


def read_lock(settings: Settings) -> dict[str, Any] | None:
    path = get_lock_path(settings)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())  # type: ignore[no-any-return]
    except json.JSONDecodeError:
        return {"pid": path.read_text().strip(), "task_id": None}


def release_lock(settings: Settings) -> None:
    path = get_lock_path(settings)
    path.unlink(missing_ok=True)
    logger.info("finetune lock released", path=str(path))
