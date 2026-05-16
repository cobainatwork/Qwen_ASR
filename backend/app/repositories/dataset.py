from sqlalchemy import func, select
from sqlalchemy.orm import Session

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

    def __init__(self, db: Session, api_key_id: int) -> None:
        self.db = db
        self.api_key_id = api_key_id

    def list_by_dataset(
        self, dataset_id: int, limit: int = 50, offset: int = 0
    ) -> list[DatasetSample]:
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
