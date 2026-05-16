from pathlib import Path

import pytest
import soundfile as sf
from app.core.exceptions import AudioResampleFailedError
from app.services.audio.resampler import resample_to_16k_mono

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "audio"


@pytest.mark.asyncio
async def test_16k_mono_passthrough(tmp_path: Path) -> None:
    result = await resample_to_16k_mono(FIXTURES / "valid_16k_mono.wav", tmp_path)
    assert result.original_sample_rate == 16000
    assert result.resampling_warning is False
    assert result.output_path.exists()
    data, sr = sf.read(str(result.output_path))
    assert sr == 16000
    assert data.ndim == 1


@pytest.mark.asyncio
async def test_8k_upsampling_sets_warning(tmp_path: Path) -> None:
    result = await resample_to_16k_mono(FIXTURES / "valid_8k_mono.wav", tmp_path)
    assert result.original_sample_rate == 8000
    assert result.resampling_warning is True
    _, sr = sf.read(str(result.output_path))
    assert sr == 16000


@pytest.mark.asyncio
async def test_48k_stereo_downsamples_and_mono(tmp_path: Path) -> None:
    result = await resample_to_16k_mono(FIXTURES / "valid_48k_stereo.wav", tmp_path)
    assert result.original_sample_rate == 48000
    assert result.resampling_warning is False
    data, sr = sf.read(str(result.output_path))
    assert sr == 16000
    assert data.ndim == 1


@pytest.mark.asyncio
async def test_8bit_normalised(tmp_path: Path) -> None:
    result = await resample_to_16k_mono(FIXTURES / "valid_8bit.wav", tmp_path)
    assert result.output_path.exists()
    data, sr = sf.read(str(result.output_path))
    assert sr == 16000
    assert -1.0 <= data.min() <= data.max() <= 1.0


@pytest.mark.asyncio
async def test_corrupted_raises_resample_failed(tmp_path: Path) -> None:
    with pytest.raises(AudioResampleFailedError):
        await resample_to_16k_mono(FIXTURES / "corrupted.wav", tmp_path)


@pytest.mark.asyncio
async def test_empty_raises_resample_failed(tmp_path: Path) -> None:
    with pytest.raises(AudioResampleFailedError):
        await resample_to_16k_mono(FIXTURES / "empty.wav", tmp_path)


@pytest.mark.asyncio
async def test_output_filename_is_uuid(tmp_path: Path) -> None:
    result = await resample_to_16k_mono(FIXTURES / "valid_16k_mono.wav", tmp_path)
    name = result.output_path.stem
    assert name.endswith("_16k")
    assert len(name) > len("_16k")  # 含 UUID 部分
