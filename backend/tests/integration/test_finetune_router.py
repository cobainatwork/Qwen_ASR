import pytest
from app.core.security import derive_hmac_key, hash_token, lookup_prefix
from app.deps.db import get_db
from app.middleware import register_exception_handlers
from app.routers.finetune import router as finetune_router
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session


def _build_app(db_session: Session) -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(finetune_router)
    app.dependency_overrides[get_db] = lambda: db_session
    return app


@pytest.fixture
def finetune_app(
    db_session: Session, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> tuple[FastAPI, str, int]:
    monkeypatch.setenv("API_KEY", "ft-test")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@h/d")
    monkeypatch.setenv("DB_PASSWORD", "p")
    monkeypatch.setenv("THIRD_PARTY_LICENSE_ACK", "true")
    monkeypatch.setenv("AUDIO_STORAGE_DIR", str(tmp_path))
    monkeypatch.setenv("FINETUNE_LOCK_PATH", str(tmp_path / "ft.lock"))
    from app.core.config import get_settings
    get_settings.cache_clear()

    # patch subprocess 啟動為 no-op（避免實際 Python 子程序）
    async def _fake_start(**kwargs):  # type: ignore[no-untyped-def]
        import asyncio
        async def _noop() -> int:
            return 0
        return asyncio.create_task(_noop())

    monkeypatch.setattr("app.routers.finetune.start_finetune_subprocess", _fake_start)

    raw_token = "ft-token"
    hmac_key = derive_hmac_key("ft-test")
    db_session.execute(
        text("TRUNCATE api_keys, datasets, finetune_tasks, finetune_checkpoints CASCADE")
    )
    db_session.execute(
        text(
            "INSERT INTO api_keys (key_hash, lookup_prefix, name, scopes) "
            "VALUES (:h, :p, 'ftk', '{asr:read,asr:write,admin}')"
        ),
        {"h": hash_token(raw_token), "p": lookup_prefix(raw_token, hmac_key)},
    )
    api_key_id = db_session.execute(text("SELECT id FROM api_keys WHERE name = 'ftk'")).scalar_one()
    # 建一個 dataset 供 task 引用
    db_session.execute(
        text("INSERT INTO datasets (api_key_id, name) VALUES (:a, 'ds1')"),
        {"a": api_key_id},
    )
    dataset_id = db_session.execute(text("SELECT id FROM datasets WHERE name = 'ds1'")).scalar_one()
    db_session.commit()
    return _build_app(db_session), raw_token, int(dataset_id)


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_create_task_starts_subprocess(finetune_app) -> None:
    app, token, dataset_id = finetune_app
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/finetune/tasks",
            json={"name": "exp1", "dataset_id": dataset_id, "base_model": "Qwen/Qwen3-ASR-1.7B"},
            headers=_headers(token),
        )
    assert resp.status_code == 201
    assert resp.json()["data"]["status"] == "preparing"
    assert resp.json()["data"]["name"] == "exp1"


def test_create_second_task_rejected(finetune_app) -> None:
    app, token, dataset_id = finetune_app
    with TestClient(app) as client:
        client.post(
            "/api/v1/finetune/tasks",
            json={"name": "exp1", "dataset_id": dataset_id},
            headers=_headers(token),
        )
        resp2 = client.post(
            "/api/v1/finetune/tasks",
            json={"name": "exp2", "dataset_id": dataset_id},
            headers=_headers(token),
        )
    assert resp2.status_code == 409
    assert resp2.json()["error"]["code"] == "FINETUNE_CONCURRENT"


def test_list_tasks(finetune_app) -> None:
    app, token, dataset_id = finetune_app
    with TestClient(app) as client:
        client.post(
            "/api/v1/finetune/tasks",
            json={"name": "exp1", "dataset_id": dataset_id},
            headers=_headers(token),
        )
        resp = client.get("/api/v1/finetune/tasks", headers=_headers(token))
    assert resp.status_code == 200
    assert len(resp.json()["data"]) == 1


def test_get_task_not_found(finetune_app) -> None:
    app, token, _ = finetune_app
    with TestClient(app) as client:
        resp = client.get("/api/v1/finetune/tasks/9999", headers=_headers(token))
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "FINETUNE_TASK_NOT_FOUND"


def test_upload(finetune_app) -> None:
    app, token, _ = finetune_app
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/finetune/upload",
            files={"file": ("data.csv", b"header\nrow1\n", "text/csv")},
            headers=_headers(token),
        )
    assert resp.status_code == 201
    assert resp.json()["data"]["size_bytes"] > 0


def test_promote_checkpoint(finetune_app, db_session: Session) -> None:
    app, token, dataset_id = finetune_app
    with TestClient(app) as client:
        create_resp = client.post(
            "/api/v1/finetune/tasks",
            json={"name": "exp1", "dataset_id": dataset_id},
            headers=_headers(token),
        )
        task_id = create_resp.json()["data"]["id"]
        # 手動 INSERT 一個 checkpoint（runner 子程序不會真的寫）
        db_session.execute(
            text(
                "INSERT INTO finetune_checkpoints "
                "(task_id, epoch, step, loss, checkpoint_path, file_size) "
                "VALUES (:t, 3, 300, 0.5, '/tmp/ckpt.bin', 1024)"
            ),
            {"t": task_id},
        )
        ckpt_id = db_session.execute(
            text("SELECT id FROM finetune_checkpoints WHERE task_id = :t ORDER BY id DESC"),
            {"t": task_id},
        ).scalar_one()
        db_session.commit()

        resp = client.post(
            f"/api/v1/finetune/tasks/{task_id}/promote?checkpoint_id={ckpt_id}",
            headers=_headers(token),
        )
    assert resp.status_code == 200
    assert resp.json()["data"]["is_active"] is True
