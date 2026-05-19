"""Idempotency-Key 24h 處理（CLAUDE.md 強制規範 #7）。

V1：in-process dict + monotonic clock（規格 §3.1 workers=1，單 worker 安全）。
V2：Redis-backed，預留至 Phase 3。
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from threading import Lock
from typing import Any

from fastapi import Header, Request

from app.models import ApiKey


@dataclass(frozen=True)
class IdempotencyKey:
    """Tenant-scoped cache key：api_key_id 隔離不同租戶，header_value 為 client 指定字串。"""

    api_key_id: int
    header_value: str


class IdempotencyCache:
    """單 worker 內 Idempotency-Key 暫存。

    record() 寫入 (response, ts)；lookup() 在 TTL 內回 response，否則 None
    並清除過期條目。dict 配 Lock 防 thread race（雖然 workers=1 + asyncio 單線程，
    pytest threading 仍可能並發）。
    """

    def __init__(self, ttl_seconds: int = 86400) -> None:
        self._ttl = ttl_seconds
        self._store: dict[IdempotencyKey, tuple[Any, float]] = {}
        self._lock = Lock()

    def lookup(self, key: IdempotencyKey) -> Any | None:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            response, ts = entry
            if time.monotonic() - ts > self._ttl:
                self._store.pop(key, None)
                return None
            return response

    def record(self, key: IdempotencyKey, response: Any) -> None:
        with self._lock:
            self._store[key] = (response, time.monotonic())


_cache_singleton: IdempotencyCache | None = None


def get_idempotency_cache() -> IdempotencyCache:
    """Module-level singleton。lifespan / 測試可呼叫 reset_for_test 清空。"""
    global _cache_singleton
    if _cache_singleton is None:
        _cache_singleton = IdempotencyCache()
    return _cache_singleton


def reset_for_test() -> None:
    """測試輔助：清空 singleton。"""
    global _cache_singleton
    _cache_singleton = None


def idempotent(
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> None:
    """FastAPI dependency：套在 POST 端點。

    流程：
    1. 若無 header → 直接 return（不啟用 idempotency）。
    2. 需要 request.state.api_key 已被 require_scope 注入（順序依賴）。
    3. cache hit → 把 cached response 暫存於 request.state.idempotency_cached，
       並把 key 暫存於 request.state.idempotency_key，由 router 自行判斷是否
       直接回傳快取或進入 pipeline 後寫入 cache。
    """
    if idempotency_key is None:
        return
    api_key: ApiKey | None = getattr(request.state, "api_key", None)
    if api_key is None:
        # require_scope 尚未填 api_key，視為 unauthenticated path（auth dep 之後仍會擋 401）
        return
    cache = get_idempotency_cache()
    key = IdempotencyKey(api_key_id=api_key.id, header_value=idempotency_key)
    cached = cache.lookup(key)
    request.state.idempotency_key = key
    request.state.idempotency_cached = cached
