from __future__ import annotations

import time

import pytest
from app.core.idempotency import IdempotencyCache, IdempotencyKey


@pytest.fixture
def cache() -> IdempotencyCache:
    return IdempotencyCache(ttl_seconds=2)


def test_first_request_records_and_lookup_returns_none(cache: IdempotencyCache) -> None:
    key = IdempotencyKey(api_key_id=1, header_value="abc")
    assert cache.lookup(key) is None
    cache.record(key, response={"id": 7})


def test_replay_within_ttl_returns_cached(cache: IdempotencyCache) -> None:
    key = IdempotencyKey(api_key_id=1, header_value="abc")
    cache.record(key, response={"id": 7})
    assert cache.lookup(key) == {"id": 7}


def test_replay_after_ttl_returns_none(cache: IdempotencyCache) -> None:
    key = IdempotencyKey(api_key_id=1, header_value="abc")
    cache.record(key, response={"id": 7})
    time.sleep(2.1)
    assert cache.lookup(key) is None


def test_different_api_key_does_not_share_cache(cache: IdempotencyCache) -> None:
    cache.record(IdempotencyKey(api_key_id=1, header_value="abc"), response={"id": 7})
    assert cache.lookup(IdempotencyKey(api_key_id=2, header_value="abc")) is None
