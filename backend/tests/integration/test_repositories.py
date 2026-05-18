import pytest
from app.models import AudioFile, Transcription
from app.repositories.base import TenantScopedRepository
from sqlalchemy.orm import Session


class AudioFileRepository(TenantScopedRepository[AudioFile]):
    model = AudioFile


class TranscriptionRepository(TenantScopedRepository[Transcription]):
    model = Transcription


@pytest.fixture
def second_api_key(db_session: Session) -> int:
    from sqlalchemy import text

    db_session.execute(
        text(
            "INSERT INTO api_keys (key_hash, lookup_prefix, name, scopes) "
            "VALUES ('$argon2id$dummy2', 'abcdef0123456789', 'test-key-2', '{asr:read}')"
        )
    )
    row = db_session.execute(text("SELECT id FROM api_keys WHERE name = 'test-key-2'")).first()
    assert row is not None
    return int(row[0])


def test_create_audio_file_attaches_api_key_id(db_session: Session, seed_api_key: int) -> None:
    repo = AudioFileRepository(db_session, seed_api_key)
    af = repo.create(
        original_name="a.wav",
        storage_path="/data/audio/abc.wav",
        file_size=1024,
    )
    assert af.api_key_id == seed_api_key


def test_tenant_isolation_get(
    db_session: Session, seed_api_key: int, second_api_key: int
) -> None:
    repo_a = AudioFileRepository(db_session, seed_api_key)
    af = repo_a.create(original_name="a.wav", storage_path="/x/a.wav", file_size=1)

    repo_b = AudioFileRepository(db_session, second_api_key)
    assert repo_b.get(af.id) is None


def test_tenant_isolation_list(
    db_session: Session, seed_api_key: int, second_api_key: int
) -> None:
    AudioFileRepository(db_session, seed_api_key).create(
        original_name="a.wav", storage_path="/x/a.wav", file_size=1
    )
    AudioFileRepository(db_session, second_api_key).create(
        original_name="b.wav", storage_path="/x/b.wav", file_size=2
    )
    assert len(AudioFileRepository(db_session, seed_api_key).list()) == 1
    assert len(AudioFileRepository(db_session, second_api_key).list()) == 1


def test_update_blocks_cross_tenant(
    db_session: Session, seed_api_key: int, second_api_key: int
) -> None:
    repo_a = AudioFileRepository(db_session, seed_api_key)
    af = repo_a.create(original_name="a.wav", storage_path="/x/a.wav", file_size=1)

    repo_b = AudioFileRepository(db_session, second_api_key)
    with pytest.raises(PermissionError):
        repo_b.update(af, original_name="hack.wav")


def test_update_applies_changes_within_tenant(
    db_session: Session, seed_api_key: int
) -> None:
    """同租戶 update 通過 cross-tenant 守衛 → 套用變更 → flush 寫回。

    覆蓋 base.py:40 False 分支 + 42-45（setattr 迴圈 + flush）。
    """
    repo = AudioFileRepository(db_session, seed_api_key)
    af = repo.create(original_name="orig.wav", storage_path="/x/orig.wav", file_size=1)

    updated = repo.update(af, original_name="renamed.wav", file_size=999)

    assert updated.original_name == "renamed.wav"
    assert updated.file_size == 999
    # flush 後從 DB 讀回（同 session 但確認 attribute 已套用）
    refetched = repo.get(af.id)
    assert refetched is not None
    assert refetched.original_name == "renamed.wav"
    assert refetched.file_size == 999


def test_delete_within_tenant_removes_row(
    db_session: Session, seed_api_key: int
) -> None:
    """同租戶 delete：cross-tenant 守衛 PASS → db.delete + flush。

    覆蓋 base.py:48 False 分支 + 50-51（db.delete + flush）。
    """
    repo = AudioFileRepository(db_session, seed_api_key)
    af = repo.create(original_name="tmp.wav", storage_path="/x/tmp.wav", file_size=1)
    af_id = af.id

    repo.delete(af)

    assert repo.get(af_id) is None


def test_delete_blocks_cross_tenant(
    db_session: Session, seed_api_key: int, second_api_key: int
) -> None:
    """跨租戶 delete 觸發 PermissionError，且 row 必須仍存在。

    覆蓋 base.py:48 True 分支 + 49（raise PermissionError）。
    """
    repo_a = AudioFileRepository(db_session, seed_api_key)
    af = repo_a.create(original_name="a.wav", storage_path="/x/a.wav", file_size=1)

    repo_b = AudioFileRepository(db_session, second_api_key)
    with pytest.raises(PermissionError, match="跨租戶 delete"):
        repo_b.delete(af)

    # 守衛擋下後 row 必須仍在；用 owner 視角確認
    assert repo_a.get(af.id) is not None
