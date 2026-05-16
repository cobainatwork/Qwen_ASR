from pathlib import Path

import pytest
from app.core.exceptions import AudioMimeInvalidError
from app.services.audio.mime import verify_mime

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "audio"
SUPPORTED = ["wav", "mp3", "mp4", "flac", "aac", "ogg", "m4a"]


def _read(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def test_valid_wav_passes() -> None:
    mime, ext = verify_mime(_read("valid_16k_mono.wav"), SUPPORTED)
    assert mime in {"audio/wav", "audio/x-wav"}
    assert ext == "wav"


def test_empty_buffer_rejected() -> None:
    with pytest.raises(AudioMimeInvalidError, match="檔案為空"):
        verify_mime(b"", SUPPORTED)


def test_zip_disguised_as_wav_rejected() -> None:
    with pytest.raises(AudioMimeInvalidError) as exc:
        verify_mime(_read("fake_extension.wav.zip"), SUPPORTED)
    assert exc.value.code == "AUDIO_MIME_INVALID"
    assert "detected_mime" in (exc.value.details or {})
    assert "audio" not in (exc.value.details or {}).get("detected_mime", "")


def test_unsupported_format_rejected() -> None:
    # 縮減白名單模擬不支援 wav
    with pytest.raises(AudioMimeInvalidError, match="不在白名單"):
        verify_mime(_read("valid_16k_mono.wav"), ["mp3"])


def test_corrupted_wav_still_detected_as_audio() -> None:
    # 部分 WAV header 仍可被 libmagic 辨識；但實際解碼會於 Task 3.4 失敗
    # 此測試確保 MIME 層不過度嚴格（讓重取樣層回 AUDIO_RESAMPLE_FAILED 而非 MIME_INVALID）
    buf = _read("corrupted.wav")
    if buf.startswith(b"RIFF"):
        _mime, ext = verify_mime(buf, SUPPORTED)
        assert ext == "wav"
