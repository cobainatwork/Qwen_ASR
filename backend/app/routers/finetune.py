from __future__ import annotations

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
from app.models import ApiKey, FinetuneCheckpoint, FinetuneTask
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


def _to_task_data(task: FinetuneTask) -> FinetuneTaskData:
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


def _to_ckpt_data(ckpt: FinetuneCheckpoint) -> FinetuneCheckpointData:
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
        raise FinetuneCheckpointNotFoundError(
            details={"task_id": task_id, "checkpoint_id": checkpoint_id}
        )

    try:
        ckpt_repo.activate(checkpoint_id)
        db.commit()
    except Exception as e:
        raise FinetunePromoteFailedError(details={"error": str(e)}) from e

    return success(_to_ckpt_data(ckpt))
