"""產生 backend/tests/fixtures/audio/ 內所有測試音檔。

執行：python scripts/generate_audio_fixtures.py
依賴：numpy, soundfile（已在 dev 依賴內）
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import numpy as np
import soundfile as sf

OUT_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "audio"


def _sine_wave(duration_sec: float, freq: float, sample_rate: int, channels: int = 1) -> np.ndarray:
    t = np.linspace(0, duration_sec, int(sample_rate * duration_sec), endpoint=False)
    mono = 0.5 * np.sin(2 * np.pi * freq * t).astype(np.float32)
    if channels == 1:
        return mono
    return np.stack([mono, mono * 0.8], axis=1)


def _silence(duration_sec: float, sample_rate: int) -> np.ndarray:
    return np.zeros(int(sample_rate * duration_sec), dtype=np.float32)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # 16 kHz mono 1 秒
    sf.write(OUT_DIR / "valid_16k_mono.wav", _sine_wave(1.0, 440, 16000), 16000, subtype="PCM_16")

    # 8 kHz mono 1 秒（觸發 resampling_warning）
    sf.write(OUT_DIR / "valid_8k_mono.wav", _sine_wave(1.0, 440, 8000), 8000, subtype="PCM_16")

    # 48 kHz stereo 1 秒（觸發降採樣 + mono）
    sf.write(
        OUT_DIR / "valid_48k_stereo.wav",
        _sine_wave(1.0, 440, 48000, channels=2),
        48000,
        subtype="PCM_16",
    )

    # 8-bit unsigned PCM（強制轉 16-bit）
    sf.write(OUT_DIR / "valid_8bit.wav", _sine_wave(1.0, 440, 16000), 16000, subtype="PCM_U8")

    # 全零靜音（觸發 AUDIO_NO_SPEECH）
    sf.write(OUT_DIR / "silence.wav", _silence(1.0, 16000), 16000, subtype="PCM_16")

    # 損壞檔（WAV header 但 body 截斷）
    valid = _sine_wave(1.0, 440, 16000)
    sf.write(OUT_DIR / "_temp_full.wav", valid, 16000, subtype="PCM_16")
    full_bytes = (OUT_DIR / "_temp_full.wav").read_bytes()
    (OUT_DIR / "corrupted.wav").write_bytes(full_bytes[:200])  # 截斷 header
    (OUT_DIR / "_temp_full.wav").unlink()

    # 副檔名偽裝：實際是 zip
    with zipfile.ZipFile(OUT_DIR / "fake_extension.wav.zip", "w") as zf:
        zf.writestr("inside.txt", "I am a zip, not audio.")

    # 空檔案
    (OUT_DIR / "empty.wav").write_bytes(b"")

    # 列印產出
    for f in sorted(OUT_DIR.glob("*")):
        if f.is_file() and f.name != "README.md":
            print(f"created: {f.name} ({f.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
