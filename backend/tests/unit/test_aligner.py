from pathlib import Path

import pytest
from app.core.exceptions import AlignerAudioTooLongError, AlignerNotReadyError
from app.services.aligner.service import AlignerService, WordTimestamp


class _FakeAligner:
    def align(self, text: str, wav_path: str) -> list[tuple[str, float, float]]:
        return [("你好", 0.0, 0.5), ("世界", 0.5, 1.0)]


@pytest.fixture(autouse=True)
def _reset() -> None:
    AlignerService.set_engine_for_test(None)
    yield
    AlignerService.set_engine_for_test(None)


@pytest.mark.asyncio
async def test_align_returns_word_timestamps(tmp_path: Path) -> None:
    AlignerService.set_engine_for_test(_FakeAligner(), max_duration_sec=300)
    result = await AlignerService.align("你好世界", tmp_path / "fake.wav", duration_sec=1.0)
    assert len(result) == 2
    assert result[0] == WordTimestamp(word="你好", start_sec=0.0, end_sec=0.5)


@pytest.mark.asyncio
async def test_align_not_ready_raises(tmp_path: Path) -> None:
    AlignerService.set_engine_for_test(None)
    with pytest.raises(AlignerNotReadyError):
        await AlignerService.align("test", tmp_path / "fake.wav", duration_sec=1.0)


@pytest.mark.asyncio
async def test_align_audio_too_long_raises(tmp_path: Path) -> None:
    AlignerService.set_engine_for_test(_FakeAligner(), max_duration_sec=300)
    with pytest.raises(AlignerAudioTooLongError) as exc:
        await AlignerService.align("test", tmp_path / "fake.wav", duration_sec=301.0)
    assert exc.value.details["limit_sec"] == 300
    assert exc.value.details["actual_sec"] == 301.0
