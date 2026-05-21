import os
from collections.abc import Generator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from testcontainers.postgres import PostgresContainer


@pytest.fixture(scope="session")
def postgres_url() -> Generator[str, None, None]:
    """啟動 qwen-asr-postgres:test 容器（需先 docker build postgres/）。"""
    image = os.environ.get("TEST_POSTGRES_IMAGE", "qwen-asr-postgres:test")
    with PostgresContainer(image, username="test", password="test", dbname="qwen_asr_test") as pg:
        yield pg.get_connection_url(driver="psycopg")


@pytest.fixture(scope="session")
def db_engine(postgres_url: str) -> Generator[Engine, None, None]:
    """初始化 schema：直接 alembic upgrade head。

    env.py 讀取 DATABASE_URL 環境變數並覆寫 cfg.set_main_option，導致
    testcontainers DB URL 被生產 DB URL 取代。修正方式：暫時 unset
    DATABASE_URL，確保 alembic 使用 cfg 中設定的 testcontainers URL。
    """
    from alembic import command
    from alembic.config import Config

    engine = create_engine(postgres_url, future=True)
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", postgres_url)

    # Temporarily remove DATABASE_URL so alembic/env.py does not override the
    # testcontainers URL with the production database URL.
    saved_db_url = os.environ.pop("DATABASE_URL", None)
    try:
        command.upgrade(cfg, "head")
    finally:
        if saved_db_url is not None:
            os.environ["DATABASE_URL"] = saved_db_url

    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine: Engine) -> Generator[Session, None, None]:
    """每測試獨立交易，結束時 rollback。"""
    connection = db_engine.connect()
    transaction = connection.begin()
    SessionLocal = sessionmaker(bind=connection, expire_on_commit=False, future=True)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def seed_api_key(db_session: Session) -> int:
    """建立一個測試 API key，回傳 id。"""
    db_session.execute(
        text(
            "INSERT INTO api_keys (key_hash, lookup_prefix, name, scopes) "
            "VALUES (:h, :p, :n, :s)"
        ),
        {
            "h": "$argon2id$dummy",
            "p": "1234567890abcdef",
            "n": "test-key",
            "s": "{asr:read,asr:write}",
        },
    )
    row = db_session.execute(text("SELECT id FROM api_keys WHERE name = 'test-key'")).first()
    assert row is not None
    return int(row[0])
