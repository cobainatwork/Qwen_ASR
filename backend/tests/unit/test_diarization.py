from pathlib import Path

import pytest
from app.core.config import Settings
from app.core.exceptions import DiarizationFailedError, DiarizationNotReadyError
from app.services.diarization.service import (
    DiarizationService,
    SpeakerSegment,
)


def _settings(backend: str = "pyannote") -> Settings:
    return Settings(
        API_KEY="t",
        DATABASE_URL="postgresql+psycopg://u:p@h/d",
        DB_PASSWORD="p",
        THIRD_PARTY_LICENSE_ACK=True,
        DIARIZATION_BACKEND=backend,
        FINETUNE_LOCK_PATH=Path("/tmp/no-such-lock"),
    )  # type: ignore[call-arg]


@pytest.fixture(autouse=True)
def _reset() -> None:
    DiarizationService.set_backends_for_test(None, None, None)
    yield
    DiarizationService.set_backends_for_test(None, None, None)


@pytest.mark.asyncio
async def test_diarize_pyannote(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    settings = _settings("pyannote")
    DiarizationService.set_backends_for_test(pyannote=object(), settings=settings)

    def _fake_run(_pipe, _wav):  # type: ignore[no-untyped-def]
        return [("SPK_00", 0.0, 1.0), ("SPK_01", 1.0, 2.0)]

    monkeypatch.setattr("app.services.diarization._pyannote.run_pyannote", _fake_run)

    segments, backend = await DiarizationService.diarize(tmp_path / "x.wav")
    assert backend == "pyannote"
    assert len(segments) == 2
    assert segments[0] == SpeakerSegment(speaker="SPK_00", start_sec=0.0, end_sec=1.0)


@pytest.mark.asyncio
async def test_diarize_finetune_force_campp(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    lock_path = tmp_path / "finetune.lock"
    lock_path.write_text("123")
    settings = _settings("pyannote")
    settings = settings.model_copy(update={"FINETUNE_LOCK_PATH": lock_path})

    fake_campp = object()
    DiarizationService.set_backends_for_test(pyannote=None, campp=fake_campp, settings=settings)

    def _fake_run(_pipe, _wav):  # type: ignore[no-untyped-def]
        return [("S1", 0.0, 0.5)]

    monkeypatch.setattr("app.services.diarization._campp.run_campp", _fake_run)

    segments, backend = await DiarizationService.diarize(tmp_path / "x.wav")
    assert backend == "campp"
    assert len(segments) == 1


@pytest.mark.asyncio
async def test_diarize_not_ready(tmp_path: Path) -> None:
    settings = _settings("pyannote")
    DiarizationService.set_backends_for_test(pyannote=None, settings=settings)
    with pytest.raises(DiarizationNotReadyError):
        await DiarizationService.diarize(tmp_path / "x.wav")


@pytest.mark.asyncio
async def test_diarize_propagates_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    settings = _settings("pyannote")
    DiarizationService.set_backends_for_test(pyannote=object(), settings=settings)

    def _fake_run(_pipe, _wav):  # type: ignore[no-untyped-def]
        raise RuntimeError("inference failed")

    monkeypatch.setattr("app.services.diarization._pyannote.run_pyannote", _fake_run)

    with pytest.raises(DiarizationFailedError) as exc:
        await DiarizationService.diarize(tmp_path / "x.wav")
    assert exc.value.details["backend"] == "pyannote"
