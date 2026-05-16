from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, status
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.core.exceptions import NotFoundError
from app.core.response import success
from app.deps.auth import require_scope
from app.deps.db import get_db, get_session_factory
from app.models import ApiKey, YoutubeDownload
from app.repositories.audio_file import AudioFileRepository
from app.repositories.youtube import YoutubeDownloadRepository
from app.schemas.common import ResponseEnvelope
from app.schemas.youtube import YoutubeDownloadData, YoutubeDownloadRequest
from app.services.youtube import download_audio, validate_youtube_url

router = APIRouter(prefix="/api/v1/dataset/youtube", tags=["youtube"])


def _to_data(d: YoutubeDownload) -> YoutubeDownloadData:
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
    db_session_factory: sessionmaker[Session],
    settings: Settings,
) -> None:
    """背景下載任務：下載 YouTube 音檔並寫回 DB。"""
    from app.services.audio.storage import store_upload

    with db_session_factory() as db:
        repo = YoutubeDownloadRepository(db, api_key_id)
        record = repo.get(download_id)
        if record is None:
            return
        audio_path_to_cleanup: Path | None = None
        try:
            record.status = "downloading"
            db.commit()
            result = await download_audio(
                url, settings.AUDIO_STORAGE_DIR / "youtube", settings
            )
            audio_path_to_cleanup = result.audio_path
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
            # store_upload 完成後所有權已轉移，不再由本函式負責清理
            audio_path_to_cleanup = None
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
        except Exception as e:
            record.status = "failed"
            record.error_message = str(e)[:1000]
            db.commit()
            if audio_path_to_cleanup is not None:
                audio_path_to_cleanup.unlink(missing_ok=True)


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

    background.add_task(
        _execute_download,
        record.id,
        url,
        api_key.id,
        get_session_factory(),
        settings,
    )

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
    repo = YoutubeDownloadRepository(db, api_key.id)
    record = repo.get(download_id)
    if record is None:
        raise NotFoundError(message="YouTube 下載紀錄不存在")
    return success(_to_data(record))
