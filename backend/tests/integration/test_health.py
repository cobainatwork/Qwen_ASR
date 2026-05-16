from app.deps.db import get_db
from app.routers.health import router as health_router
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def _build_app(db_session: Session) -> FastAPI:
    app = FastAPI()
    app.include_router(health_router)
    app.dependency_overrides[get_db] = lambda: db_session
    return app


def test_health_endpoint(db_session: Session) -> None:
    client = TestClient(_build_app(db_session))
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["status"] == "ok"
    assert body["data"]["version"] == "0.1.0"
    assert body["error"] is None


def test_readiness_with_db_ok(db_session: Session) -> None:
    client = TestClient(_build_app(db_session))
    resp = client.get("/readiness")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["status"] == "ok"
    assert body["data"]["checks"]["database"] == "ok"
