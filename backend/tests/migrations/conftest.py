"""Migration-test fixtures.

Provides ``alembic_cfg`` separately from the session-scoped ``db_engine``
so migration tests can drive upgrade/downgrade themselves.
"""
from __future__ import annotations

import pytest
from alembic.config import Config


@pytest.fixture
def alembic_cfg(postgres_url: str) -> Config:
    """Return an Alembic Config wired to the test database."""
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", postgres_url)
    return cfg
