from sqlalchemy import select
from sqlalchemy.orm import Session

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

    def append_loss(self, task_id: int, entry: dict[str, object]) -> None:
        task = self.get(task_id)
        if task is None:
            return
        history = list(task.loss_history or [])
        history.append(entry)
        task.loss_history = history
        self.db.flush()


class FinetuneCheckpointRepository:
    """Checkpoint 跨 task 存取（Tenant 透過 task → api_key_id 驗證）。"""

    def __init__(self, db: Session, api_key_id: int) -> None:
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
            select(FinetuneCheckpoint)
            .where(FinetuneCheckpoint.task_id == task_id)
            .order_by(FinetuneCheckpoint.epoch)
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
