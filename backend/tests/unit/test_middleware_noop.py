import pytest
from app.middleware import (
    idempotency_middleware,
    prometheus_middleware,
    rate_limit_middleware,
    request_id_middleware,
    tracing_middleware,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _build_app_with_middleware(middleware) -> FastAPI:
    app = FastAPI()
    app.middleware("http")(middleware)

    @app.get("/ping")
    def ping() -> dict:
        return {"pong": True}

    return app


def test_request_id_middleware_returns_header() -> None:
    app = _build_app_with_middleware(request_id_middleware)
    resp = TestClient(app).get("/ping")
    assert resp.status_code == 200
    assert "X-Request-ID" in resp.headers


def test_request_id_middleware_uses_provided_id() -> None:
    app = _build_app_with_middleware(request_id_middleware)
    resp = TestClient(app).get("/ping", headers={"X-Request-ID": "abc-123"})
    assert resp.headers["X-Request-ID"] == "abc-123"


@pytest.mark.parametrize(
    "mw",
    [prometheus_middleware, tracing_middleware, rate_limit_middleware, idempotency_middleware],
)
def test_noop_middlewares_are_passthrough(mw) -> None:
    app = _build_app_with_middleware(mw)
    resp = TestClient(app).get("/ping")
    assert resp.status_code == 200
    assert resp.json() == {"pong": True}


@pytest.mark.phase2
def test_prometheus_middleware_records_metrics() -> None:
    pytest.skip("Phase 2 啟用 Prometheus 後再驗證")


@pytest.mark.phase2
def test_rate_limit_middleware_enforces_limit() -> None:
    pytest.skip("Phase 2 啟用 slowapi 後再驗證")
