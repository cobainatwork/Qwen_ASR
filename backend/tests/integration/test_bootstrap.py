"""bootstrap_admin_key 整合測試。

注意：bootstrap_admin_key 內部呼叫 db.commit()，
會提交外層交易，與 conftest db_session 的 rollback 策略衝突。
因此本模組使用獨立的 sessionmaker（非 conftest 的 db_session），
每個測試自行管理 transaction 並於結束後清理資料。
"""

import pytest
from app.core.config import Settings
from app.services.bootstrap import bootstrap_admin_key
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker


def _settings(api_key: str = "boot-token") -> Settings:
    return Settings(
        API_KEY=api_key,
        DATABASE_URL="postgresql+psycopg://u:p@h/d",
        DB_PASSWORD="p",
        THIRD_PARTY_LICENSE_ACK=True,
    )  # type: ignore[call-arg]


@pytest.fixture
def clean_session(db_engine: Engine) -> Session:  # type: ignore[misc]
    """建立獨立的 session，使用後清理 api_keys 與 audit_logs。"""
    SessionLocal = sessionmaker(bind=db_engine, expire_on_commit=False, future=True)
    session = SessionLocal()
    # 清理測試隔離：先清空兩張表，確保每次測試獨立
    session.execute(text("TRUNCATE api_keys, audit_logs CASCADE"))
    session.commit()
    yield session
    # 測試後清理
    session.execute(text("TRUNCATE api_keys, audit_logs CASCADE"))
    session.commit()
    session.close()


def test_bootstrap_creates_admin_when_empty(clean_session: Session) -> None:
    """api_keys 表為空時，bootstrap 應建立 bootstrap-admin 金鑰並寫入 audit event。"""
    bootstrap_admin_key(clean_session, _settings())

    row = clean_session.execute(
        text("SELECT name, scopes FROM api_keys WHERE name = 'bootstrap-admin'")
    ).first()
    assert row is not None
    assert "admin" in row[1]

    audit = clean_session.execute(
        text("SELECT event_type FROM audit_logs WHERE event_type = 'auth.key_created'")
    ).first()
    assert audit is not None


def test_bootstrap_skips_when_keys_exist(clean_session: Session) -> None:
    """api_keys 表非空時，bootstrap 不應新增任何金鑰。"""
    # 在 clean_session 內自行插入一筆資料模擬「非空」情況。
    # 不使用 seed_api_key fixture：該 fixture 依賴 db_session（rollback 模式），
    # 兩個 session 同時持鎖會造成 TRUNCATE 與 INSERT 相互死鎖。
    clean_session.execute(
        text(
            "INSERT INTO api_keys (key_hash, lookup_prefix, name, scopes) "
            "VALUES ('$argon2id$dummy', '1234567890abcdef', 'existing-key', '{asr:read}')"
        )
    )
    clean_session.commit()

    before = clean_session.execute(text("SELECT COUNT(*) FROM api_keys")).scalar_one()
    bootstrap_admin_key(clean_session, _settings())
    after = clean_session.execute(text("SELECT COUNT(*) FROM api_keys")).scalar_one()
    assert before == after
