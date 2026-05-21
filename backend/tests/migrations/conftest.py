"""Migration-test fixtures — fully self-contained.

Strategy:
- In container env (DATABASE_URL set): the entrypoint already ran
  alembic upgrade head. Fixtures simply connect to the live DB and yield
  the engine. No migration state changes are made during setup.
- In local dev (DATABASE_URL not set): spin up testcontainers postgres,
  run upgrade head to 0004 baseline, yield; teardown restores to head.

This design avoids disrupting the running production database.
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

_IN_CONTAINER = bool(os.environ.get("DATABASE_URL", "").strip())
_BASELINE_REVISION = "0004"


def _container_db_url() -> str:
    return os.environ["DATABASE_URL"]


@pytest.fixture(scope="module")
def migration_db_url() -> Generator[str, None, None]:
    """Yield a database URL for migration tests."""
    if _IN_CONTAINER:
        yield _container_db_url()
        return

    # Local dev: spin up testcontainers.
    try:
        import testcontainers  # noqa: F401  # type: ignore[import]
    except ImportError as exc:
        raise RuntimeError(
            "testcontainers not installed and DATABASE_URL not set. "
            "Either set DATABASE_URL or install testcontainers."
        ) from exc

    from testcontainers.postgres import PostgresContainer  # type: ignore[import]

    image = os.environ.get("TEST_POSTGRES_IMAGE", "qwen-asr-postgres:test")
    with PostgresContainer(
        image, username="test", password="test", dbname="qwen_asr_test"
    ) as pg:
        yield pg.get_connection_url(driver="psycopg")


@pytest.fixture(scope="module")
def migration_engine(migration_db_url: str) -> Generator[Engine, None, None]:
    """Yield a SQLAlchemy engine connected to the migration test DB.

    Container env: DB is already at head (entrypoint applied migrations).
    Local dev: upgrade to baseline revision first; restore to head on teardown.
    """
    engine = create_engine(migration_db_url, future=True)
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", migration_db_url)

    if not _IN_CONTAINER:
        # Fresh testcontainers DB: bring to head then downgrade to baseline
        # so individual tests can drive the migration under test.
        command.upgrade(cfg, "head")
        command.downgrade(cfg, _BASELINE_REVISION)

    yield engine

    if not _IN_CONTAINER:
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
    """Per-test session (no transaction isolation — DDL commits immediately)."""
    SessionLocal = sessionmaker(bind=migration_engine, expire_on_commit=False, future=True)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
