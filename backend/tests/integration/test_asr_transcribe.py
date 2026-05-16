"""
transcribe 端點端對端整合測試（mock vLLM）。

注入策略：
- _MockEngine 取代 vLLM AsyncLLMEngine
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

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.security import derive_hmac_key, hash_token, lookup_prefix
from app.deps.db import get_db
from app.middleware import register_exception_handlers
from app.routers.asr import router as asr_router
from app.services.asr.engine import AsrEngineManager
from app.services.asr.queue import AsrJob, AsyncioQueueBackend
from app.services.asr.transcriber import Transcriber
from app.services.audio.vad import FireRedVADService

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "audio"


class _MockEngine:
    """vLLM AsyncLLMEngine 替身：固定回傳測試文字。"""

    async def generate(self, **kwargs) -> dict:  # type: ignore[no-untyped-def]
        return {"text": "你好世界，這是測試辨識結果。", "timestamps": None}

    async def abort_all(self) -> None:
        return None


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

    # 注入 mock engine / VAD
    AsrEngineManager.set_engine_for_test(_MockEngine(), model_version="MOCK@TEST")
    FireRedVADService.set_model(_FakeVadModel())

    # patch wait_for_job：改為直接在 event loop 內執行 Transcriber
    # 避免 AsrConsumer background task 的 sync psycopg 阻塞 event loop
    async def _inline_wait_for_job(job: AsrJob, timeout: float) -> int:
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
    AsrEngineManager.set_engine_for_test(None)
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
    """傳入 diarization / nec_enabled → 回應 warnings 包含相應欄位名稱。"""
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
    assert any("diarization" in w for w in warnings)
    assert any("nec_enabled" in w for w in warnings)


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
