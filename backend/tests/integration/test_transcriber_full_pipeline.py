"""Transcriber 端到端整合測試（M7 Task 7.6）。

驗證四個後處理階段全部寫入 JSONB 欄位：
  1. AlignerService.align（mock）
  2. DiarizationService.diarize（mock pyannote）
  3. run_post_processing（標點 + 數字正規化）
  4. run_correction_pipeline（同音糾錯）

文字流程：
  「我在試一次」
    → 後處理 punctuation → 「我在試一次。」
    → 後處理 numbers   → 「我在試1次。」
    → 糾錯 homophone   → 「我再試1次。」（在→再）
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from app.repositories.audio_file import AudioFileRepository
from app.services.aligner import AlignerService
from app.services.asr.engine import AsrEngineManager
from app.services.asr.queue import AsrJob
from app.services.asr.transcriber import Transcriber
from app.services.correction.homophone import HomophoneCorrector
from app.services.diarization import DiarizationService
from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "audio"


class _MockEngine:
    """vLLM 替身：固定回傳測試文字與 None timestamps。"""

    async def generate(self, **kwargs: Any) -> dict[str, Any]:
        return {"text": "我在試一次", "timestamps": None}

    async def abort_all(self) -> None:
        pass


class _FakeAligner:
    """ForcedAligner 替身：回傳固定 5 個字的時間戳記。"""

    def align(self, text: str, wav_path: str) -> list[tuple[str, float, float]]:
        return [
            ("我", 0.0, 0.2),
            ("在", 0.2, 0.4),
            ("試", 0.4, 0.6),
            ("一", 0.6, 0.8),
            ("次", 0.8, 1.0),
        ]


class _FakeDiarizationPyannote:
    """pyannote Pipeline 替身（佔位物件，實際呼叫由 monkeypatch 攔截）。"""


@pytest.fixture(autouse=True)
def _setup(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Any:
    """注入所有 mock 並在測試結束後清理。"""
    # 注入 ASR 引擎
    AsrEngineManager.set_engine_for_test(_MockEngine(), model_version="MOCK@FULL")
    # 注入 Aligner
    AlignerService.set_engine_for_test(_FakeAligner(), max_duration_sec=300)
    # 啟用同音糾錯，自訂對照表（在→再）
    HomophoneCorrector.configure(True, custom_map={"在": "再"})

    # 攔截 run_pyannote（diarize 內部動態 import 後呼叫）
    monkeypatch.setattr(
        "app.services.diarization._pyannote.run_pyannote",
        lambda _p, _w: [("SPK_00", 0.0, 1.0)],
    )

    # 建立假設定（避免讀取 .env）
    from app.core.config import Settings

    fake_settings = Settings(
        API_KEY="t",
        DATABASE_URL="postgresql+psycopg://u:p@h/d",
        DB_PASSWORD="p",
        THIRD_PARTY_LICENSE_ACK=True,
        ALIGNER_ENABLED=True,
        DIARIZATION_ENABLED=True,
        DIARIZATION_BACKEND="pyannote",
        POST_PROCESSING_ENABLED=True,
        CORRECTION_HOMOPHONE_ENABLED=True,
        FINETUNE_LOCK_PATH=tmp_path / "no-such-lock-m7",
    )  # type: ignore[call-arg]

    # 注入 DiarizationService 後端
    DiarizationService.set_backends_for_test(
        pyannote=_FakeDiarizationPyannote(),
        settings=fake_settings,
    )

    # 替換 get_settings（先保留原始函式參考以供 teardown 呼叫 cache_clear）
    import app.core.config as _config_mod

    _original_get_settings = _config_mod.get_settings
    _original_get_settings.cache_clear()
    monkeypatch.setattr("app.core.config.get_settings", lambda: fake_settings)

    yield

    # --- 清理 ---
    AsrEngineManager.set_engine_for_test(None)
    AlignerService.set_engine_for_test(None)
    DiarizationService.set_backends_for_test(None, None, None)
    HomophoneCorrector.configure(False)
    _original_get_settings.cache_clear()


def _seed_audio(db: Session, api_key_id: int) -> int:
    """在資料庫建立測試用音檔記錄，回傳 audio_file.id。"""
    repo = AudioFileRepository(db, api_key_id)
    af = repo.create(
        original_name="x.wav",
        storage_path=str(FIXTURES / "valid_16k_mono.wav"),
        file_size=1,
    )
    repo.update_after_resample(af.id, original_sample_rate=16000, duration_sec=1.0)
    db.commit()
    return af.id


@pytest.mark.asyncio
async def test_full_pipeline_writes_all_jsonb_fields(
    db_session: Session, seed_api_key: int
) -> None:
    """全 pipeline 執行後，四個 JSONB 欄位皆正確寫入。

    預期文字轉換順序：
      「我在試一次」→ 後處理 → 「我在試1次。」→ 糾錯同音 → 「我再試1次。」
    """
    audio_id = _seed_audio(db_session, seed_api_key)
    transcriber = Transcriber(db_session, seed_api_key, max_duration_sec=1200)
    outcome = await transcriber.run(
        AsrJob(
            audio_file_id=audio_id,
            api_key_id=seed_api_key,
            options={"return_timestamps": True},
        )
    )

    row = db_session.execute(
        sa_text(
            "SELECT transcript_text, timestamps, speakers, post_processing "
            "FROM transcriptions WHERE id = :i"
        ),
        {"i": outcome.transcription_id},
    ).first()
    assert row is not None
    transcript, timestamps, speakers, post = row

    # 文字：後處理（數字正規化將「一」轉為「1」）+ 同音糾錯（在→再）
    assert transcript == "我再試1次。"

    # Aligner：5 個字的 word-level timestamps
    assert isinstance(timestamps, list)
    assert len(timestamps) == 5

    # Diarization：1 個 speaker segment
    assert isinstance(speakers, list)
    assert len(speakers) == 1
    assert speakers[0]["speaker"] == "SPK_00"

    # JSONB 各階段記錄
    assert post["aligner"]["status"] == "ok"
    assert post["aligner"]["count"] == 5

    assert post["diarization"]["status"] == "ok"
    assert post["diarization"]["backend"] == "pyannote"
    assert post["diarization"]["speakers"] == 1

    assert post["post_processing"]["stages"][0]["stage"] == "punctuation"
    assert post["post_processing"]["stages"][0]["status"] == "ok"

    assert post["correction"]["stages"][0]["layer"] == "homophone"
    assert post["correction"]["stages"][0]["status"] == "ok"
