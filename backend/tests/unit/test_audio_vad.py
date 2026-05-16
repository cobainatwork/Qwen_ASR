from pathlib import Path

import pytest
from app.core.exceptions import (
    AudioNoSpeechError,
    AudioVadFailedError,
    AudioVadNotReadyError,
)
from app.services.audio.vad import FireRedVADService, Segment


class _FakeModel:
    def __init__(self, segments: list[tuple[float, float]] | Exception) -> None:
        self._segments = segments

    def infer(self, wav_path: str) -> list[tuple[float, float]]:
        if isinstance(self._segments, Exception):
            raise self._segments
        return self._segments


@pytest.fixture(autouse=True)
def _reset_vad_model() -> None:
    FireRedVADService.set_model(None)
    yield
    FireRedVADService.set_model(None)


@pytest.mark.asyncio
async def test_detect_speech_returns_segments(tmp_path: Path) -> None:
    FireRedVADService.set_model(_FakeModel([(0.0, 1.0), (1.5, 2.5)]))
    result = await FireRedVADService.detect_speech(tmp_path / "fake.wav")
    assert len(result) == 2
    assert result[0] == Segment(start_sec=0.0, end_sec=1.0)


@pytest.mark.asyncio
async def test_detect_speech_empty_raises_no_speech(tmp_path: Path) -> None:
    FireRedVADService.set_model(_FakeModel([]))
    with pytest.raises(AudioNoSpeechError):
        await FireRedVADService.detect_speech(tmp_path / "fake.wav")


@pytest.mark.asyncio
async def test_detect_speech_not_ready_raises(tmp_path: Path) -> None:
    FireRedVADService.set_model(None)
    with pytest.raises(AudioVadNotReadyError):
        await FireRedVADService.detect_speech(tmp_path / "fake.wav")


@pytest.mark.asyncio
async def test_detect_speech_propagates_failure(tmp_path: Path) -> None:
    FireRedVADService.set_model(_FakeModel(RuntimeError("inference broke")))
    with pytest.raises(AudioVadFailedError) as exc:
        await FireRedVADService.detect_speech(tmp_path / "fake.wav")
    assert "inference broke" in str(exc.value.details)
