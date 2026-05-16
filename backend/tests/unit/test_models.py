from app.models import ApiKey, AudioFile, AuditLog, Base, Transcription


def test_all_models_subclass_base() -> None:
    assert issubclass(ApiKey, Base)
    assert issubclass(AudioFile, Base)
    assert issubclass(Transcription, Base)
    assert issubclass(AuditLog, Base)


def test_tenant_models_have_api_key_id() -> None:
    assert "api_key_id" in AudioFile.__table__.columns
    assert "api_key_id" in Transcription.__table__.columns


def test_api_keys_table_columns() -> None:
    cols = {c.name for c in ApiKey.__table__.columns}
    expected = {
        "id", "key_hash", "lookup_prefix", "name", "description",
        "scopes", "created_by_key_id", "rate_limit_override",
        "is_active", "created_at", "expires_at", "deleted_at", "last_used_at",
    }
    assert expected <= cols


def test_audit_logs_metadata_column_aliased() -> None:
    # 屬性名 metadata_ 但 DB 欄位名 metadata
    col = AuditLog.__table__.columns["metadata"]
    assert col.name == "metadata"
