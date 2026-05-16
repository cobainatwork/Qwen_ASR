from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import DatasetNotFoundError
from app.core.response import success
from app.deps.auth import require_scope
from app.deps.db import get_db
from app.models import ApiKey, Dataset, DatasetSample
from app.repositories.dataset import DatasetRepository, DatasetSampleRepository
from app.schemas.common import ResponseEnvelope
from app.schemas.dataset import DatasetCreate, DatasetData, DatasetSampleData
from app.services.dataset import process_sample

router = APIRouter(prefix="/api/v1/dataset", tags=["dataset"])


def _to_data(dataset: Dataset) -> DatasetData:
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


def _to_sample_data(sample: DatasetSample) -> DatasetSampleData:
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
