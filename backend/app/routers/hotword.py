from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.exceptions import HotwordGroupNotFoundError
from app.core.response import success
from app.deps.auth import require_scope
from app.deps.db import get_db
from app.models import ApiKey, HotwordGroup
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


def _to_data(group: HotwordGroup) -> HotwordGroupData:
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
