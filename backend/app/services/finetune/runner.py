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
import sys
from pathlib import Path
from typing import Any

import structlog

from app.core.config import Settings
from app.services.finetune.data_augmentation import AugmentationPlan
from app.services.finetune.lock import acquire_lock, release_lock

logger = structlog.get_logger(__name__)

# 模組頂層計算腳本路徑，避免在 async 函式內呼叫 pathlib（ASYNC240）
_FINETUNE_SCRIPT = str(
    Path(__file__).resolve().parent.parent.parent.parent / "scripts" / "finetune_runner.py"
)


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

    augment = AugmentationPlan.from_config(settings.DATA_AUGMENTATION_ENABLED)

    cmd = [
        sys.executable,
        _FINETUNE_SCRIPT,
        "--task-id", str(task_id),
        "--dataset-id", str(dataset_id),
        "--base-model", base_model,
        "--config", json.dumps(config),
        "--gpu-fraction", str(settings.FINETUNE_GPU_FRACTION),
        *augment.to_runner_args(),
    ]

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
            logger.info(
                "finetune subprocess exited", task_id=task_id, returncode=proc.returncode
            )

    return asyncio.create_task(_monitor(), name=f"finetune-monitor-{task_id}")
