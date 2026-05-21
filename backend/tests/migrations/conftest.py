"""Migration-test fixtures — fully self-contained.

Strategy:
- When DATABASE_URL is set (running inside the asr-backend container),
  use it directly after downgrading to the pre-migration baseline.
- When DATABASE_URL is not set (local dev), spin up testcontainers postgres.

This avoids depending on the main conftest's testcontainers-based postgres_url
fixture, which requires Docker socket access not available inside the container.
"""
from __future__ import annotations

import os
from collections.abc import Generator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

# Revision just before the migration under test.
_BASELINE_REVISION = "0004"


def _get_db_url() -> str:
    """Return the database URL for migration tests.

    Prefers DATABASE_URL env (container environment).
    Falls back to testcontainers postgres for local dev.
    """
    env_url = os.environ.get("DATABASE_URL")
    if env_url:
        return env_url
    # Local dev: spin up testcontainers.
    try:
        import testcontainers  # noqa: F401  # type: ignore[import]
    except ImportError as exc:
        raise RuntimeError(
            "testcontainers not installed and DATABASE_URL not set. "
            "Either set DATABASE_URL or install testcontainers."
        ) from exc
    image = os.environ.get("TEST_POSTGRES_IMAGE", "qwen-asr-postgres:test")
    raise _NeedTestcontainersError(image)


class _NeedTestcontainersError(Exception):
    def __init__(self, image: str) -> None:
        self.image = image


@pytest.fixture(scope="module")
def migration_db_url() -> Generator[str, None, None]:
    """Yield a database URL for migration tests."""
    try:
        url = _get_db_url()
        yield url
    except _NeedTestcontainersError as exc:
        from testcontainers.postgres import PostgresContainer  # type: ignore[import]

        with PostgresContainer(
            exc.image, username="test", password="test", dbname="qwen_asr_test"
        ) as pg:
            yield pg.get_connection_url(driver="psycopg")


@pytest.fixture(scope="module")
def migration_engine(migration_db_url: str) -> Generator[Engine, None, None]:
    """Engine initialised at baseline revision (0004), ready for upgrade tests."""
    engine = create_engine(migration_db_url, future=True)
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", migration_db_url)
    # Bring DB to head first (in case it's a fresh testcontainers DB),
    # then downgrade to the baseline before this migration.
    command.upgrade(cfg, "head")
    command.downgrade(cfg, _BASELINE_REVISION)
    yield engine
    # Restore to head after the module finishes.
    command.upgrade(cfg, "head")
    engine.dispose()


@pytest.fixture(scope="module")
def alembic_cfg(migration_db_url: str) -> Config:
    """Alembic Config wired to the migration test database."""
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", migration_db_url)
    return cfg


@pytest.fixture
def mig_session(migration_engine: Engine) -> Generator[Session, None, None]:
    """Per-test session with rollback isolation (DML only; DDL not rolled back)."""
    connection = migration_engine.connect()
    transaction = connection.begin_nested()
    SessionLocal = sessionmaker(bind=connection, expire_on_commit=False, future=True)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
