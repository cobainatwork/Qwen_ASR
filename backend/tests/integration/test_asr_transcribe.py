"""
transcribe 端點端對端整合測試（mock qwen-asr 引擎）。

注入策略：
- _MockAsrModel 取代 Qwen3ASRModel.LLM（qwen-asr 0.0.6 介面）
- _FakeVadModel 取代 FireRedVAD
- monkeypatch 替換 app.routers.asr.wait_for_job，讓 Transcriber.run()
  直接在測試 event loop 內以 db_session 執行（無需 AsrConsumer background task）
- TRUNCATE api_keys 後 INSERT 真實 Argon2id hash + lookup_prefix
- 不啟動 consumer，避免 sync psycopg 阻塞 asyncio event loop

event loop 問題說明：
  AsrConsumer 使用 synchronous SQLAlchemy session，若在 anyio blocking portal
  （TestClient 的 event loop）中直接呼叫會阻塞 event loop，導致 router 的
  wait_for_job 永遠無法被 scheduled。解決方式：patch wait_for_job，在 event loop
  內 await Transcriber.run()（mock engine 即時返回，同步 DB 操作快速完成）。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.core.security import derive_hmac_key, hash_token, lookup_prefix
from app.deps.db import get_db
from app.middleware import register_exception_handlers
from app.routers.asr import router as asr_router
from app.services.asr.engine import AsrEngineManager
from app.services.asr.queue import AsrJob, AsyncioQueueBackend
from app.services.asr.transcriber import Transcriber
from app.services.audio.vad import FireRedVADService
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "audio"


class _MockAsrModel:
    """Qwen3ASRModel.LLM 替身（qwen-asr 0.0.6 介面）：transcribe 為同步方法。"""

    def transcribe(self, audio: Any, **kwargs: Any) -> list[Any]:
        result = MagicMock()
        result.text = "你好世界，這是測試辨識結果。"
        result.language = "Chinese"
        result.time_stamps = None
        return [result]


class _FakeVadModel:
    """FireRedVAD 模型替身：固定回傳一個語音段。"""

    def infer(self, wav_path: str) -> list[tuple[float, float]]:
        return [(0.0, 1.0)]


@pytest.fixture
def app_with_asr(
    db_session: Session, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> tuple[FastAPI, str]:
    """
    建立含 ASR 路由的最小 FastAPI app，並注入 mock engine / VAD。

    consumer 未啟動：改為 patch wait_for_job，讓 Transcriber.run() 直接
    在測試 event loop 內執行（db_session 同步 IO 在 TestClient 的 anyio
    event loop 內快速完成，不需要 background task）。
    """
    monkeypatch.setenv("API_KEY", "smoke-bootstrap")
    monkeypatch.setenv("DATABASE_URL", str(db_session.bind.engine.url))
    monkeypatch.setenv("DB_PASSWORD", "test")
    monkeypatch.setenv("THIRD_PARTY_LICENSE_ACK", "true")
    monkeypatch.setenv("AUDIO_STORAGE_DIR", str(tmp_path))
    monkeypatch.setenv("SUPPORTED_AUDIO_FORMATS", "wav,mp3")
    monkeypatch.setenv("MAX_UPLOAD_SIZE_MB", "100")

    from app.core.config import get_settings
    from app.deps.db import get_engine, get_session_factory

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()

    # 建立有效 token
    raw_token = "real-test-token-x"
    hmac_key = derive_hmac_key("smoke-bootstrap")
    db_session.execute(
        text("TRUNCATE api_keys, audio_files, transcriptions, audit_logs CASCADE")
    )
    db_session.execute(
        text(
            "INSERT INTO api_keys (key_hash, lookup_prefix, name, scopes) "
            "VALUES (:h, :p, 't', '{asr:write}')"
        ),
        {"h": hash_token(raw_token), "p": lookup_prefix(raw_token, hmac_key)},
    )
    db_session.commit()

    # 注入 mock ASR / VAD
    AsrEngineManager.set_asr_for_test(_MockAsrModel(), model_version="MOCK@TEST")
    FireRedVADService.set_model(_FakeVadModel())

    # patch wait_for_job：改為直接在 event loop 內執行 Transcriber
    # 避免 AsrConsumer background task 的 sync psycopg 阻塞 event loop
    # ASYNC109 noqa：簽章必須匹配 real app.routers.asr.wait_for_job(job, timeout)
    # 才能被 monkeypatch.setattr 取代；mock 內部立即返回故 timeout 參數不使用。
    async def _inline_wait_for_job(job: AsrJob, timeout: float) -> int:  # noqa: ASYNC109
        transcriber = Transcriber(db_session, job.api_key_id, max_duration_sec=1200)
        outcome = await transcriber.run(job)
        return outcome.transcription_id

    monkeypatch.setattr("app.routers.asr.wait_for_job", _inline_wait_for_job)

    # 建立 FastAPI app（僅含 ASR 路由）
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(asr_router)
    app.dependency_overrides[get_db] = lambda: db_session

    # 設定 queue（路由透過 request.app.state.asr_queue 取得）
    queue = AsyncioQueueBackend(realtime_max=5, batch_max=5)
    app.state.asr_queue = queue

    yield app, raw_token

    # 清理
    AsrEngineManager.set_asr_for_test(None)
    FireRedVADService.set_model(None)


@pytest.mark.timeout(60)
def test_transcribe_endpoint_returns_text(app_with_asr: tuple[FastAPI, str]) -> None:
    """成功流程：上傳 16k WAV → 200 + text=固定值 + model_version=MOCK@TEST。"""
    app, token = app_with_asr
    with TestClient(app) as client:
        with (FIXTURES / "valid_16k_mono.wav").open("rb") as f:
            resp = client.post(
                "/api/v1/asr/transcribe",
                files={"file": ("a.wav", f, "audio/wav")},
                data={
                    "options_json": json.dumps(
                        {"language": "zh-TW", "return_timestamps": False}
                    )
                },
                headers={"Authorization": f"Bearer {token}"},
            )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["text"] == "你好世界，這是測試辨識結果。"
    assert body["data"]["model_version"] == "MOCK@TEST"
    assert body["data"]["resampling_warning"] is False


@pytest.mark.timeout(60)
def test_transcribe_warns_unsupported_options(app_with_asr: tuple[FastAPI, str]) -> None:
    """傳入 nec_enabled → warnings 應包含 nec_enabled；diarization 不再列為 unsupported。"""
    app, token = app_with_asr
    with TestClient(app) as client:
        with (FIXTURES / "valid_16k_mono.wav").open("rb") as f:
            resp = client.post(
                "/api/v1/asr/transcribe",
                files={"file": ("a.wav", f, "audio/wav")},
                data={
                    "options_json": json.dumps(
                        {"diarization": True, "nec_enabled": True}
                    )
                },
                headers={"Authorization": f"Bearer {token}"},
            )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    warnings = body["data"]["warnings"]
    assert any("nec_enabled" in w for w in warnings)
    # diarization 由 settings 控制（M7 起支援），不應再列為「Phase 1 不支援」
    assert not any("diarization" in w for w in warnings), warnings


@pytest.mark.timeout(60)
def test_transcribe_surfaces_diarization(
    app_with_asr: tuple[FastAPI, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """DIARIZATION_ENABLED=True 時，response 暴露 speakers list 與 diarization.backend。"""
    from app.core.config import get_settings
    from app.services.diarization import DiarizationService

    monkeypatch.setattr(
        "app.services.diarization._pyannote.run_pyannote",
        lambda _p, _w: [("SPK_00", 0.0, 0.5), ("SPK_01", 0.5, 1.0)],
    )
    DiarizationService.set_backends_for_test(
        pyannote=object(),  # 佔位，實際呼叫已被 monkeypatch 攔截
        settings=get_settings(),
    )
    try:
        app, token = app_with_asr
        with TestClient(app) as client:
            with (FIXTURES / "valid_16k_mono.wav").open("rb") as f:
                resp = client.post(
                    "/api/v1/asr/transcribe",
                    files={"file": ("a.wav", f, "audio/wav")},
                    data={"options_json": json.dumps({"return_timestamps": False})},
                    headers={"Authorization": f"Bearer {token}"},
                )
        assert resp.status_code == 200, resp.text
        body = resp.json()["data"]
        speakers = body["speakers"]
        assert speakers is not None and len(speakers) == 2
        assert speakers[0] == {"speaker": "SPK_00", "start": 0.0, "end": 0.5}
        assert body["diarization"] == {
            "status": "ok",
            "backend": "pyannote",
            "speakers_count": 2,
        }
    finally:
        DiarizationService.set_backends_for_test(None, None, None)


@pytest.mark.timeout(60)
def test_transcribe_8k_audio_sets_resampling_warning(
    app_with_asr: tuple[FastAPI, str],
) -> None:
    """上傳 8kHz WAV → resampling_warning 應為 True。"""
    app, token = app_with_asr
    with TestClient(app) as client:
        with (FIXTURES / "valid_8k_mono.wav").open("rb") as f:
            resp = client.post(
                "/api/v1/asr/transcribe",
                files={"file": ("a.wav", f, "audio/wav")},
                data={"options_json": "{}"},
                headers={"Authorization": f"Bearer {token}"},
            )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["resampling_warning"] is True


@pytest.mark.timeout(60)
def test_transcribe_rejects_zip_disguised_as_wav(
    app_with_asr: tuple[FastAPI, str],
) -> None:
    """上傳 zip 偽裝的 .wav → 400 AUDIO_MIME_INVALID。"""
    app, token = app_with_asr
    with TestClient(app) as client:
        with (FIXTURES / "fake_extension.wav.zip").open("rb") as f:
            resp = client.post(
                "/api/v1/asr/transcribe",
                files={"file": ("a.wav", f, "audio/wav")},
                data={"options_json": "{}"},
                headers={"Authorization": f"Bearer {token}"},
            )
    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert body["error"]["code"] == "AUDIO_MIME_INVALID"


@pytest.mark.timeout(60)
def test_transcribe_unauthenticated_returns_401(
    app_with_asr: tuple[FastAPI, str],
) -> None:
    """無 Authorization header → 401。"""
    app, _ = app_with_asr
    with TestClient(app) as client:
        with (FIXTURES / "valid_16k_mono.wav").open("rb") as f:
            resp = client.post(
                "/api/v1/asr/transcribe",
                files={"file": ("a.wav", f, "audio/wav")},
                data={"options_json": "{}"},
            )
    assert resp.status_code == 401, resp.text


# ── /transcribe-stored/{audio_file_id} ──────────────────────────────────


@pytest.mark.timeout(60)
def test_transcribe_stored_returns_text(app_with_asr: tuple[FastAPI, str]) -> None:
    """既存 audio_file → /transcribe-stored/{id} 回 200 + 固定 text。

    流程：先用 /transcribe 上傳取得 audio_file_id，再用 /transcribe-stored
    對同一個 audio 重跑 ASR（模擬 YouTube 下載完成後一鍵辨識）。
    """
    app, token = app_with_asr
    with TestClient(app) as client:
        with (FIXTURES / "valid_16k_mono.wav").open("rb") as f:
            upload = client.post(
                "/api/v1/asr/transcribe",
                files={"file": ("a.wav", f, "audio/wav")},
                data={"options_json": "{}"},
                headers={"Authorization": f"Bearer {token}"},
            )
        assert upload.status_code == 200, upload.text
        audio_file_id = upload.json()["data"]["audio_file_id"]

        resp = client.post(
            f"/api/v1/asr/transcribe-stored/{audio_file_id}",
            data={"options_json": json.dumps({"language": "Chinese"})},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["text"] == "你好世界，這是測試辨識結果。"
    assert body["data"]["audio_file_id"] == audio_file_id
    assert body["data"]["model_version"] == "MOCK@TEST"


@pytest.mark.timeout(60)
def test_transcribe_stored_not_found(app_with_asr: tuple[FastAPI, str]) -> None:
    """不存在的 audio_file_id → 404 RESOURCE_NOT_FOUND。"""
    app, token = app_with_asr
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/asr/transcribe-stored/99999",
            data={"options_json": "{}"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 404, resp.text


@pytest.mark.timeout(60)
def test_transcribe_stored_cross_tenant_blocked(
    app_with_asr: tuple[FastAPI, str], db_session: Session
) -> None:
    """跨租戶 audio_file 必須回 404（不洩漏存在性，不可回 403）。"""
    other_token = "other-tenant-token"
    other_hmac = derive_hmac_key("smoke-bootstrap")
    db_session.execute(
        text(
            "INSERT INTO api_keys (key_hash, lookup_prefix, name, scopes) "
            "VALUES (:h, :p, 'other', '{asr:write}') RETURNING id"
        ),
        {
            "h": hash_token(other_token),
            "p": lookup_prefix(other_token, other_hmac),
        },
    )
    other_key_id = db_session.execute(
        text("SELECT id FROM api_keys WHERE name = 'other'")
    ).scalar_one()
    db_session.execute(
        text(
            "INSERT INTO audio_files "
            "(api_key_id, original_name, storage_path, file_size) "
            "VALUES (:k, 'other.wav', '/tmp/nonexistent.wav', 100) RETURNING id"
        ),
        {"k": other_key_id},
    )
    foreign_audio_id = db_session.execute(
        text(
            "SELECT id FROM audio_files WHERE api_key_id = :k ORDER BY id DESC"
        ),
        {"k": other_key_id},
    ).scalar_one()
    db_session.commit()

    app, my_token = app_with_asr
    with TestClient(app) as client:
        resp = client.post(
            f"/api/v1/asr/transcribe-stored/{foreign_audio_id}",
            data={"options_json": "{}"},
            headers={"Authorization": f"Bearer {my_token}"},
        )
    assert resp.status_code == 404, resp.text


@pytest.mark.timeout(60)
def test_transcribe_stored_unauthenticated_returns_401(
    app_with_asr: tuple[FastAPI, str],
) -> None:
    """無 Authorization header → 401。"""
    app, _ = app_with_asr
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/asr/transcribe-stored/1",
            data={"options_json": "{}"},
        )
    assert resp.status_code == 401, resp.text


@pytest.mark.timeout(60)
@pytest.mark.xfail(
    strict=False,
    reason=(
        "app_with_asr fixture 共用單一 db_session；多 thread 並發時 SQLAlchemy "
        "Session.flush() 會互相碰撞（'Session is already flushing'）。此為 test "
        "fixture 結構性限制，不反映 production 行為（production 每個請求有獨立 "
        "Session + 獨立 DB connection，SELECT FOR UPDATE 真正阻塞生效）。"
        "測試保留為 regression rail：若未來重構讓共用 session 消失，此測試應自動轉 PASS。"
    ),
)
def test_transcribe_stored_concurrent_calls_complete_without_error(
    app_with_asr: tuple[FastAPI, str],
) -> None:
    """同一 audio_file_id 並發 transcribe-stored 必須序列化執行（SELECT FOR UPDATE）。

    驗證點：兩個 thread 同時打 /transcribe-stored，最終都拿到 200（或第二個 409）；
    結果不可有 unhandled 500、不可有 DB constraint violation、不可有未捕獲例外。
    Mock ASR 引擎極快，無法用 timing 確切驗證序列化是否生效；改以「兩個請求都正常結束」
    為契約鎖。
    """
    import threading

    app, token = app_with_asr
    # 先 seed 一個 audio_file
    with TestClient(app) as client:
        with (FIXTURES / "valid_16k_mono.wav").open("rb") as f:
            upload = client.post(
                "/api/v1/asr/transcribe",
                files={"file": ("a.wav", f, "audio/wav")},
                data={"options_json": "{}"},
                headers={"Authorization": f"Bearer {token}"},
            )
        assert upload.status_code == 200, upload.text
        audio_file_id = upload.json()["data"]["audio_file_id"]

    results: list[tuple[int, str]] = []  # (status_code, body_text_or_error)

    def call() -> None:
        with TestClient(app) as client:
            r = client.post(
                f"/api/v1/asr/transcribe-stored/{audio_file_id}",
                data={"options_json": "{}"},
                headers={"Authorization": f"Bearer {token}"},
            )
            results.append((r.status_code, r.text[:200]))

    t1 = threading.Thread(target=call)
    t2 = threading.Thread(target=call)
    t1.start()
    t2.start()
    t1.join(timeout=30)
    t2.join(timeout=30)

    assert len(results) == 2, f"both threads must finish; got results={results}"
    # 任何 5xx 即視為鎖實作有 bug
    for status_code, body in results:
        assert status_code < 500, f"unexpected 5xx: status={status_code} body={body}"
