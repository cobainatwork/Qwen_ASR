import pytest
from app.core.security import derive_hmac_key, hash_token, lookup_prefix
from app.deps.db import get_db
from app.middleware import register_exception_handlers
from app.routers.correction import router as correction_router
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session


def _build_app(db_session: Session) -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(correction_router)
    app.dependency_overrides[get_db] = lambda: db_session
    return app


@pytest.fixture
def corr_app(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> tuple[FastAPI, str, int, int]:
    monkeypatch.setenv("API_KEY", "corr-test")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@h/d")
    monkeypatch.setenv("DB_PASSWORD", "p")
    monkeypatch.setenv("THIRD_PARTY_LICENSE_ACK", "true")
    from app.core.config import get_settings
    get_settings.cache_clear()

    raw_token = "corr-token"
    hmac_key = derive_hmac_key("corr-test")
    db_session.execute(
        text(
            "TRUNCATE api_keys, transcriptions, correction_sessions, correction_segments, "
            "audio_files, datasets, dataset_samples CASCADE"
        )
    )
    db_session.execute(
        text(
            "INSERT INTO api_keys (key_hash, lookup_prefix, name, scopes) "
            "VALUES (:h, :p, 'corrk', '{asr:read,asr:write}')"
        ),
        {"h": hash_token(raw_token), "p": lookup_prefix(raw_token, hmac_key)},
    )
    api_key_id = int(
        db_session.execute(
            text("SELECT id FROM api_keys WHERE name = 'corrk'")
        ).scalar_one()
    )

    # 建立一個假 transcription + audio_file
    db_session.execute(
        text(
            "INSERT INTO audio_files "
            "(api_key_id, original_name, storage_path, file_size, duration_sec) "
            "VALUES (:a, 't.wav', '/tmp/t.wav', 1024, 10.0)"
        ),
        {"a": api_key_id},
    )
    audio_id = int(
        db_session.execute(
            text("SELECT id FROM audio_files ORDER BY id DESC LIMIT 1")
        ).scalar_one()
    )

    db_session.execute(text(
        "INSERT INTO transcriptions "
        "(api_key_id, source, model_name, model_version, transcript_text, duration_sec) "
        "VALUES (:a, 'upload', 'm', 'v1', '原始文字', 10.0)"
    ), {"a": api_key_id})
    transcription_id = int(
        db_session.execute(
            text("SELECT id FROM transcriptions ORDER BY id DESC LIMIT 1")
        ).scalar_one()
    )
    db_session.execute(text(
        "UPDATE audio_files SET transcription_id = :t WHERE id = :a"
    ), {"t": transcription_id, "a": audio_id})

    # 建立 session + 2 個 segment
    db_session.execute(text(
        "INSERT INTO correction_sessions (api_key_id, transcription_id, name) "
        "VALUES (:a, :t, 'sess')"
    ), {"a": api_key_id, "t": transcription_id})
    session_id = int(
        db_session.execute(
            text("SELECT id FROM correction_sessions ORDER BY id DESC LIMIT 1")
        ).scalar_one()
    )

    for i in range(2):
        db_session.execute(text(
            "INSERT INTO correction_segments "
            "(session_id, segment_index, start_sec, end_sec, original_text) "
            "VALUES (:s, :i, :a, :b, :t)"
        ), {"s": session_id, "i": i, "a": i * 5.0, "b": (i + 1) * 5.0, "t": f"段落{i}"})
    db_session.commit()

    return _build_app(db_session), raw_token, session_id, api_key_id


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_get_session(corr_app) -> None:
    app, token, session_id, _ = corr_app
    with TestClient(app) as client:
        resp = client.get(f"/api/v1/correction/sessions/{session_id}", headers=_headers(token))
    assert resp.status_code == 200
    assert resp.json()["data"]["name"] == "sess"


def test_list_segments(corr_app) -> None:
    app, token, session_id, _ = corr_app
    with TestClient(app) as client:
        resp = client.get(
            f"/api/v1/correction/sessions/{session_id}/segments",
            headers=_headers(token),
        )
    assert resp.status_code == 200
    assert len(resp.json()["data"]) == 2


def test_update_segment_with_correct_version(corr_app, db_session: Session) -> None:
    app, token, session_id, _ = corr_app
    seg_id = int(db_session.execute(text(
        "SELECT id FROM correction_segments WHERE session_id = :s ORDER BY segment_index LIMIT 1"
    ), {"s": session_id}).scalar_one())

    with TestClient(app) as client:
        resp = client.put(
            f"/api/v1/correction/sessions/{session_id}/segments/{seg_id}",
            json={"corrected_text": "修正後", "expected_version": 1},
            headers=_headers(token),
        )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["corrected_text"] == "修正後"
    assert data["version"] == 2

    # 驗 DB 持久化
    db_session.expire_all()
    row = db_session.execute(
        text("SELECT version, corrected_text FROM correction_segments WHERE id = :id"),
        {"id": seg_id},
    ).one()
    assert row.version == 2
    assert row.corrected_text == "修正後"


def test_update_segment_version_mismatch(corr_app, db_session: Session) -> None:
    app, token, session_id, _ = corr_app
    seg_id = int(db_session.execute(text(
        "SELECT id FROM correction_segments WHERE session_id = :s ORDER BY segment_index LIMIT 1"
    ), {"s": session_id}).scalar_one())

    with TestClient(app) as client:
        # 先 update 一次到 v2
        client.put(
            f"/api/v1/correction/sessions/{session_id}/segments/{seg_id}",
            json={"corrected_text": "first", "expected_version": 1},
            headers=_headers(token),
        )
        # 再用 v1（已過期）update
        resp = client.put(
            f"/api/v1/correction/sessions/{session_id}/segments/{seg_id}",
            json={"corrected_text": "second", "expected_version": 1},
            headers=_headers(token),
        )
    assert resp.status_code == 409
    body = resp.json()
    assert body["error"]["code"] == "CORRECTION_VERSION_MISMATCH"
    assert body["error"]["details"]["actual_version"] == 2

    # 驗 DB：第二次 stale request 未覆寫資料
    db_session.expire_all()
    row = db_session.execute(
        text("SELECT version, corrected_text FROM correction_segments WHERE id = :id"),
        {"id": seg_id},
    ).one()
    assert row.version == 2  # 第一次 update 後的版本
    assert row.corrected_text == "first"  # 第二次 stale request 未覆寫


def test_get_session_not_found(corr_app) -> None:
    app, token, _, _ = corr_app
    with TestClient(app) as client:
        resp = client.get("/api/v1/correction/sessions/9999", headers=_headers(token))
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "CORRECTION_SESSION_NOT_FOUND"


def test_export_to_dataset(corr_app, db_session: Session) -> None:
    app, token, session_id, api_key_id = corr_app

    # 建立 dataset（無 status 欄位）
    db_session.execute(
        text(
            "INSERT INTO datasets (api_key_id, name, sample_count, total_duration_sec) "
            "VALUES (:a, 'ds-export', 0, 0)"
        ),
        {"a": api_key_id},
    )
    dataset_id = int(
        db_session.execute(text("SELECT id FROM datasets WHERE name = 'ds-export'")).scalar_one()
    )
    db_session.commit()

    # 取得 2 個 segment 的 id
    seg_ids = [
        int(r) for r in db_session.execute(
            text("SELECT id FROM correction_segments WHERE session_id = :s ORDER BY segment_index"),
            {"s": session_id},
        ).scalars().all()
    ]

    with TestClient(app) as client:
        # 先 PUT 兩個 segment 填入 corrected_text
        for seg_id in seg_ids:
            client.put(
                f"/api/v1/correction/sessions/{session_id}/segments/{seg_id}",
                json={"corrected_text": f"corrected-{seg_id}", "expected_version": 1},
                headers=_headers(token),
            )

        resp = client.post(
            f"/api/v1/correction/sessions/{session_id}/export-to-dataset",
            json={"dataset_id": dataset_id},
            headers=_headers(token),
        )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["inserted_count"] == 2
    assert data["dataset_id"] == dataset_id

    # 驗 DB：dataset_samples 確實寫入 2 筆
    db_session.expire_all()
    count = int(
        db_session.execute(
            text("SELECT COUNT(*) FROM dataset_samples WHERE dataset_id = :d"),
            {"d": dataset_id},
        ).scalar_one()
    )
    assert count == 2
