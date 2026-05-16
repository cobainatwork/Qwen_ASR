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
