"""驗證 Fine-tune lock 存在時推理服務自動降級。

對應規格 §18.2：
- Aligner 跳過
- pyannote → CAM++ 強制降級
- LLM 糾錯跳過
"""

from pathlib import Path

import pytest
from app.core.config import Settings
from app.services.diarization.service import DiarizationService
from app.services.finetune.lock import (
    acquire_lock,
    is_finetune_active,
    read_lock,
    release_lock,
)


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        API_KEY="t",
        DATABASE_URL="postgresql+psycopg://u:p@h/d",
        DB_PASSWORD="p",
        THIRD_PARTY_LICENSE_ACK=True,
        FINETUNE_LOCK_PATH=tmp_path / "ft.lock",
        DIARIZATION_BACKEND="pyannote",
    )  # type: ignore[call-arg]


def test_lock_lifecycle(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    assert not is_finetune_active(settings)

    acquire_lock(settings, task_id=42)
    assert is_finetune_active(settings)
    info = read_lock(settings)
    assert info is not None
    assert info["task_id"] == 42

    release_lock(settings)
    assert not is_finetune_active(settings)


def test_lock_double_acquire_raises(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    acquire_lock(settings, task_id=1)
    with pytest.raises(RuntimeError, match="already exists"):
        acquire_lock(settings, task_id=2)
    release_lock(settings)


@pytest.mark.asyncio
async def test_diarization_forces_campp_when_lock_active(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    acquire_lock(settings, task_id=99)

    fake_campp = object()
    DiarizationService.set_backends_for_test(pyannote=object(), campp=fake_campp, settings=settings)

    def _fake_campp(_pipe, _wav):  # type: ignore[no-untyped-def]
        return [("S1", 0.0, 1.0)]

    monkeypatch.setattr("app.services.diarization._campp.run_campp", _fake_campp)

    try:
        _, backend = await DiarizationService.diarize(tmp_path / "x.wav")
        assert backend == "campp"
    finally:
        release_lock(settings)
        DiarizationService.set_backends_for_test(None, None, None)
