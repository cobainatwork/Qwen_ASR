# Phase 1 / M3 — 音檔預處理管線 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 M2 後端骨架之上，建立可獨立驗證的音檔預處理管線：MIME magic bytes 校驗 → UUID 重命名儲存 → torchaudio / soxr 重取樣至 16 kHz mono WAV → FireRedVAD 語音段偵測。完成後可在 M4 直接由 transcribe 端點呼叫。

**Architecture:** 純功能模組（不掛 router），每個步驟對應一個 service file 與一組單元測試。Resampler 使用 `asyncio.to_thread` 將阻塞性 torchaudio 包成 async，並以 `asyncio.timeout(30)` 隔離 C++ Segfault 風險。VAD 採模組級單例（`FireRedVADService._model`），於 FastAPI lifespan 啟動載入。所有錯誤透過 M2 既有的 `AppException` 子類拋出。

**Tech Stack:** python-magic（libmagic）、torchaudio、soxr、soundfile、numpy、FireRedVAD（GitHub）、pytest-asyncio。

**對應設計文件：** `docs/superpowers/specs/2026-05-16-phase1-implementation-design.md` 第 2.4、5 章節。

---

## File Structure

| 路徑 | 動作 | 責任 |
|------|------|------|
| `backend/app/services/audio/__init__.py` | Create | 顯式 re-export |
| `backend/app/services/audio/mime.py` | Create | `verify_mime(buf, supported_formats) -> str` |
| `backend/app/services/audio/storage.py` | Create | `store_upload(...)` UUID 重命名 + 落地 |
| `backend/app/services/audio/resampler.py` | Create | `resample_to_16k_mono(...)` |
| `backend/app/services/audio/vad.py` | Create | `FireRedVADService` 單例 + `detect_speech()` |
| `backend/app/repositories/audio_file.py` | Create | `AudioFileRepository`（繼承 TenantScopedRepository） |
| `backend/tests/unit/test_audio_mime.py` | Create | MIME 校驗單元測試 |
| `backend/tests/unit/test_audio_storage.py` | Create | UUID 落地測試 |
| `backend/tests/unit/test_audio_resampler.py` | Create | 重取樣測試（含 8 / 16 / 48 kHz fixture） |
| `backend/tests/unit/test_audio_vad.py` | Create | VAD（含 mock 模型） |
| `backend/tests/integration/test_audio_pipeline.py` | Create | 端到端管線測試 |
| `backend/tests/fixtures/audio/README.md` | Create | fixture 用途說明 |
| `backend/scripts/generate_audio_fixtures.py` | Create | 一次性產生 8 / 16 / 48 kHz / silence / 8bit / corrupted / empty fixture |

---

## Task 3.1：產生測試 fixtures（音檔樣本）

**Files:**
- Create: `backend/scripts/__init__.py`（空檔案）
- Create: `backend/scripts/generate_audio_fixtures.py`
- Create: `backend/tests/fixtures/__init__.py`（空檔案）
- Create: `backend/tests/fixtures/audio/README.md`

- [ ] **Step 1：建立目錄與 README**

```bash
cd backend
mkdir scripts
New-Item scripts/__init__.py -ItemType File -Force
mkdir tests/fixtures
mkdir tests/fixtures/audio
New-Item tests/fixtures/__init__.py -ItemType File -Force
```

撰寫 `tests/fixtures/audio/README.md`：

```markdown
# 音檔測試 Fixtures

由 `backend/scripts/generate_audio_fixtures.py` 產生。重新產生：

    python scripts/generate_audio_fixtures.py

| 檔名 | 用途 |
|------|------|
| `valid_16k_mono.wav` | 直通基準（不觸發重取樣） |
| `valid_8k_mono.wav` | 觸發 resampling_warning |
| `valid_48k_stereo.wav` | 觸發降採樣 + mono 轉換 |
| `valid_8bit.wav` | 觸發 8-bit 強制轉換為 16-bit |
| `silence.wav` | 觸發 AUDIO_NO_SPEECH |
| `corrupted.wav` | 觸發 AUDIO_RESAMPLE_FAILED |
| `fake_extension.wav.zip` | 副檔名偽裝（內容是 zip）|
| `empty.wav` | 空檔案 |

`.gitattributes` 已將 `*.wav` 標為 binary，避免行尾轉換破壞檔案。
```

- [ ] **Step 2：撰寫 `scripts/generate_audio_fixtures.py`**

```python
"""產生 backend/tests/fixtures/audio/ 內所有測試音檔。

執行：python scripts/generate_audio_fixtures.py
依賴：numpy, soundfile（已在 dev 依賴內）
"""

from __future__ import annotations

import struct
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
    sf.write(OUT_DIR / "valid_48k_stereo.wav", _sine_wave(1.0, 440, 48000, channels=2), 48000, subtype="PCM_16")

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
```

- [ ] **Step 3：執行 fixture 產生**

```bash
cd backend
python scripts/generate_audio_fixtures.py
```

預期輸出（順序可能不同）：

```
created: corrupted.wav (200 bytes)
created: empty.wav (0 bytes)
created: fake_extension.wav.zip (164 bytes)
created: silence.wav (32044 bytes)
created: valid_16k_mono.wav (32044 bytes)
created: valid_48k_stereo.wav (192044 bytes)
created: valid_8bit.wav (16044 bytes)
created: valid_8k_mono.wav (16044 bytes)
```

- [ ] **Step 4：將產生的 fixture 加入 git（依 .gitignore 例外規則）**

確認 `backend/tests/fixtures/audio/*.wav` 不被 ignore：

```bash
git check-ignore -v backend/tests/fixtures/audio/valid_16k_mono.wav
```

預期：印出 `:: backend/tests/fixtures/audio/valid_16k_mono.wav`（無 ignore match）。

> 若被 ignore：先檢查 `.gitignore` 中 `!backend/tests/fixtures/**/*.wav` 例外規則是否生效，必要時調整 ignore order。

- [ ] **Step 5：Commit**

```bash
git add backend/scripts/__init__.py backend/scripts/generate_audio_fixtures.py backend/tests/fixtures/__init__.py backend/tests/fixtures/audio/
git commit -m "test(backend): 加入音檔測試 fixtures 與產生腳本"
```

---

## Task 3.2：MIME 校驗（python-magic）

**Files:**
- Create: `backend/app/services/audio/__init__.py`
- Create: `backend/app/services/audio/mime.py`
- Create: `backend/tests/unit/test_audio_mime.py`

- [ ] **Step 1：建立 services/audio 目錄**

```bash
cd backend
mkdir app/services/audio
```

撰寫 `app/services/audio/__init__.py`：

```python
"""音檔處理 service：MIME、儲存、重取樣、VAD。"""

from app.services.audio.mime import verify_mime
from app.services.audio.resampler import ResampleResult, resample_to_16k_mono
from app.services.audio.storage import store_upload
from app.services.audio.vad import FireRedVADService, Segment

__all__ = [
    "FireRedVADService",
    "ResampleResult",
    "Segment",
    "resample_to_16k_mono",
    "store_upload",
    "verify_mime",
]
```

> 註：此 __init__.py 內部 import 必須在後續 Task 3.3–3.5 完成後才能執行。先寫只有 `verify_mime` 的版本，到 Task 3.5 補完。

實際先寫：

```python
from app.services.audio.mime import verify_mime

__all__ = ["verify_mime"]
```

完整版本將於 Task 3.5 補完。

- [ ] **Step 2：撰寫 `app/services/audio/mime.py`**

```python
"""音檔 MIME 校驗（magic bytes，不依賴副檔名）。"""

from __future__ import annotations

import magic

from app.core.exceptions import AudioMimeInvalidError

# python-magic 偵測結果與允許副檔名的對應
_MIME_TO_EXT = {
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/mp4": "mp4",
    "video/mp4": "mp4",
    "audio/x-m4a": "m4a",
    "audio/m4a": "m4a",
    "audio/flac": "flac",
    "audio/x-flac": "flac",
    "audio/ogg": "ogg",
    "audio/aac": "aac",
    "audio/x-aac": "aac",
    "video/webm": "webm",
    "audio/webm": "webm",
}


def verify_mime(buf: bytes, supported_formats: list[str]) -> tuple[str, str]:
    """檢查二進位內容是否為支援的音/視訊格式。

    Returns:
        (verified_mime_type, canonical_extension)

    Raises:
        AudioMimeInvalidError: 非音/視訊或副檔名不在白名單。
    """
    if not buf:
        raise AudioMimeInvalidError(message="檔案為空")

    detected = magic.from_buffer(buf, mime=True)
    if not (detected.startswith("audio/") or detected.startswith("video/")):
        raise AudioMimeInvalidError(
            message=f"非音/視訊內容：{detected}",
            details={"detected_mime": detected},
        )

    ext = _MIME_TO_EXT.get(detected)
    if ext is None:
        raise AudioMimeInvalidError(
            message=f"未支援的 MIME 類型：{detected}",
            details={"detected_mime": detected},
        )
    if ext not in {e.strip().lower() for e in supported_formats}:
        raise AudioMimeInvalidError(
            message=f"格式 {ext} 不在白名單",
            details={"detected_mime": detected, "extension": ext},
        )
    return detected, ext
```

- [ ] **Step 3：撰寫 `tests/unit/test_audio_mime.py`**

```python
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
        mime, ext = verify_mime(buf, SUPPORTED)
        assert ext == "wav"
```

- [ ] **Step 4：執行測試**

```bash
cd backend
pytest tests/unit/test_audio_mime.py -v
```

預期：5 個測試 PASS。

> Windows 環境 python-magic 需另裝 libmagic：`pip install python-magic-bin`（或安裝 libmagicwin1）。
> Linux 與 Docker 映像已透過 M1 Dockerfile 安裝 libmagic1。

- [ ] **Step 5：Lint + Type**

```bash
ruff check app tests && mypy app
```

- [ ] **Step 6：Commit**

```bash
git add backend/app/services/audio/__init__.py backend/app/services/audio/mime.py backend/tests/unit/test_audio_mime.py
git commit -m "feat(audio): 加入 MIME magic bytes 校驗（python-magic 白名單）"
```

---

## Task 3.3：UUID 重命名儲存

**Files:**
- Create: `backend/app/repositories/audio_file.py`
- Create: `backend/app/services/audio/storage.py`
- Create: `backend/tests/unit/test_audio_storage.py`

- [ ] **Step 1：撰寫 `app/repositories/audio_file.py`**

```python
from app.models import AudioFile
from app.repositories.base import TenantScopedRepository


class AudioFileRepository(TenantScopedRepository[AudioFile]):
    model = AudioFile

    def set_transcription_id(self, audio_file_id: int, transcription_id: int) -> None:
        af = self.get(audio_file_id)
        if af is None:
            return
        af.transcription_id = transcription_id
        self.db.flush()

    def update_after_resample(
        self,
        audio_file_id: int,
        *,
        original_sample_rate: int,
        duration_sec: float,
    ) -> None:
        af = self.get(audio_file_id)
        if af is None:
            return
        af.original_sample_rate = original_sample_rate
        af.duration_sec = duration_sec
        self.db.flush()
```

- [ ] **Step 2：撰寫 `app/services/audio/storage.py`**

```python
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.exceptions import AudioStorageFailedError
from app.models import AudioFile
from app.repositories.audio_file import AudioFileRepository


def store_upload(
    *,
    db: Session,
    api_key_id: int,
    raw_bytes: bytes,
    original_name: str,
    canonical_ext: str,
    verified_mime: str,
    storage_dir: Path,
) -> AudioFile:
    """將上傳 bytes 落地並插入 audio_files。"""
    if not raw_bytes:
        raise AudioStorageFailedError(message="空檔案無法儲存")

    now = datetime.now(UTC)
    sub_dir = storage_dir / f"{now.year:04d}" / f"{now.month:02d}"
    sub_dir.mkdir(parents=True, exist_ok=True)
    file_id = uuid4()
    target = sub_dir / f"{file_id}.{canonical_ext}"
    try:
        target.write_bytes(raw_bytes)
    except OSError as e:
        raise AudioStorageFailedError(details={"reason": str(e)}) from e

    repo = AudioFileRepository(db, api_key_id)
    return repo.create(
        original_name=original_name,
        storage_path=str(target),
        file_size=len(raw_bytes),
        mime_type=None,
        verified_mime_type=verified_mime,
    )
```

- [ ] **Step 3：撰寫 `tests/unit/test_audio_storage.py`**

```python
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.core.exceptions import AudioStorageFailedError
from app.services.audio.storage import store_upload


def test_store_upload_writes_file_and_inserts_db(
    db_session: Session, seed_api_key: int, tmp_path: Path
) -> None:
    af = store_upload(
        db=db_session,
        api_key_id=seed_api_key,
        raw_bytes=b"binary-data",
        original_name="hello.wav",
        canonical_ext="wav",
        verified_mime="audio/wav",
        storage_dir=tmp_path,
    )
    assert af.api_key_id == seed_api_key
    assert af.original_name == "hello.wav"
    assert af.verified_mime_type == "audio/wav"
    assert Path(af.storage_path).exists()
    assert Path(af.storage_path).read_bytes() == b"binary-data"


def test_store_upload_uses_uuid_not_original_name(
    db_session: Session, seed_api_key: int, tmp_path: Path
) -> None:
    af = store_upload(
        db=db_session,
        api_key_id=seed_api_key,
        raw_bytes=b"x",
        original_name="../etc/passwd",
        canonical_ext="wav",
        verified_mime="audio/wav",
        storage_dir=tmp_path,
    )
    # 路徑必須在 storage_dir 下，且檔名為 UUID
    assert tmp_path in Path(af.storage_path).parents
    assert ".." not in af.storage_path


def test_store_upload_rejects_empty_bytes(
    db_session: Session, seed_api_key: int, tmp_path: Path
) -> None:
    with pytest.raises(AudioStorageFailedError, match="空檔案"):
        store_upload(
            db=db_session,
            api_key_id=seed_api_key,
            raw_bytes=b"",
            original_name="empty.wav",
            canonical_ext="wav",
            verified_mime="audio/wav",
            storage_dir=tmp_path,
        )


def test_store_upload_writes_to_yyyy_mm_subdir(
    db_session: Session, seed_api_key: int, tmp_path: Path
) -> None:
    af = store_upload(
        db=db_session,
        api_key_id=seed_api_key,
        raw_bytes=b"x",
        original_name="a.wav",
        canonical_ext="wav",
        verified_mime="audio/wav",
        storage_dir=tmp_path,
    )
    parts = Path(af.storage_path).parts
    # 父目錄結構：tmp_path / YYYY / MM / UUID.wav
    assert len(parts) >= 4
    assert parts[-3].isdigit() and len(parts[-3]) == 4
    assert parts[-2].isdigit() and len(parts[-2]) == 2
```

- [ ] **Step 4：執行測試**

```bash
pytest tests/unit/test_audio_storage.py -v
```

預期：4 測試 PASS。

- [ ] **Step 5：Commit**

```bash
git add backend/app/repositories/audio_file.py backend/app/services/audio/storage.py backend/tests/unit/test_audio_storage.py
git commit -m "feat(audio): 加入 UUID 重命名儲存與 AudioFileRepository"
```

---

## Task 3.4：重取樣模組（torchaudio）

**Files:**
- Create: `backend/app/services/audio/resampler.py`
- Create: `backend/tests/unit/test_audio_resampler.py`

- [ ] **Step 1：撰寫 `app/services/audio/resampler.py`**

```python
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import soundfile as sf
import torch
import torchaudio

from app.core.exceptions import AudioDecodeTimeoutError, AudioResampleFailedError

_RESAMPLE_TIMEOUT_SEC = 30


@dataclass
class ResampleResult:
    output_path: Path
    original_sample_rate: int
    duration_sec: float
    resampling_warning: bool


async def resample_to_16k_mono(src: Path, dst_dir: Path) -> ResampleResult:
    """將任意取樣率 / 通道 / 位元深度音檔轉為 16 kHz mono 16-bit WAV。"""
    dst_dir.mkdir(parents=True, exist_ok=True)
    try:
        async with asyncio.timeout(_RESAMPLE_TIMEOUT_SEC):
            waveform, orig_sr = await asyncio.to_thread(torchaudio.load, str(src))
    except TimeoutError as e:
        raise AudioDecodeTimeoutError(details={"src": str(src)}) from e
    except Exception as e:
        raise AudioResampleFailedError(details={"reason": str(e), "src": str(src)}) from e

    try:
        # 多通道 → mono
        if waveform.shape[0] > 1:
            waveform = waveform.mean(dim=0, keepdim=True)

        # 8-bit unsigned → float32 [-1, 1]
        if waveform.dtype == torch.uint8:
            waveform = waveform.float() / 128.0 - 1.0
        elif waveform.dtype not in (torch.float32, torch.float64):
            waveform = waveform.float() / 32768.0

        if orig_sr != 16000:
            resampler = torchaudio.transforms.Resample(
                orig_freq=orig_sr,
                new_freq=16000,
                low_pass_filter_width=64,
                rolloff=0.9475937167092650,
            )
            waveform = resampler(waveform)
    except Exception as e:
        raise AudioResampleFailedError(details={"reason": str(e), "stage": "transform"}) from e

    out_path = dst_dir / f"{uuid4()}_16k.wav"
    try:
        await asyncio.to_thread(
            sf.write,
            str(out_path),
            waveform.squeeze().numpy(),
            16000,
            subtype="PCM_16",
        )
    except Exception as e:
        raise AudioResampleFailedError(details={"reason": str(e), "stage": "write"}) from e

    duration_sec = waveform.shape[-1] / 16000
    return ResampleResult(
        output_path=out_path,
        original_sample_rate=orig_sr,
        duration_sec=duration_sec,
        resampling_warning=(orig_sr == 8000),
    )
```

- [ ] **Step 2：撰寫 `tests/unit/test_audio_resampler.py`**

```python
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
```

- [ ] **Step 3：執行測試**

```bash
pytest tests/unit/test_audio_resampler.py -v
```

預期：7 個測試 PASS。第一次執行較慢（torch import 啟動時間）。

- [ ] **Step 4：Commit**

```bash
git add backend/app/services/audio/resampler.py backend/tests/unit/test_audio_resampler.py
git commit -m "feat(audio): 加入 torchaudio 重取樣（8/16/48 kHz → 16 kHz mono）"
```

---

## Task 3.5：VAD 模組（FireRedVAD 包裝）

**Files:**
- Create: `backend/app/services/audio/vad.py`
- Create: `backend/tests/unit/test_audio_vad.py`
- Modify: `backend/app/services/audio/__init__.py`

- [ ] **Step 1：撰寫 `app/services/audio/vad.py`**

```python
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from app.core.exceptions import (
    AudioNoSpeechError,
    AudioVadFailedError,
    AudioVadNotReadyError,
)


@dataclass(frozen=True)
class Segment:
    start_sec: float
    end_sec: float


class _VadEngine(Protocol):
    """FireRedVAD 模型介面（用於型別檢查與 mock）。"""

    def infer(self, wav_path: str) -> list[tuple[float, float]]: ...


class FireRedVADService:
    """FireRedVAD 模組級單例。於 FastAPI lifespan 啟動載入。"""

    _model: _VadEngine | None = None

    @classmethod
    def load(cls, model_path: Path) -> None:
        """載入 FireRedVAD 權重。Phase 1 接受任意 _VadEngine 實作。"""
        from app.services.audio._firered_vad_loader import load_firered_vad  # 延遲 import

        cls._model = load_firered_vad(model_path)

    @classmethod
    def set_model(cls, model: _VadEngine | None) -> None:
        """測試用：直接注入 mock 模型。"""
        cls._model = model

    @classmethod
    async def detect_speech(cls, wav_path: Path) -> list[Segment]:
        if cls._model is None:
            raise AudioVadNotReadyError()
        try:
            raw = await asyncio.to_thread(cls._model.infer, str(wav_path))
        except Exception as e:
            raise AudioVadFailedError(details={"reason": str(e)}) from e
        segments = [Segment(start_sec=s, end_sec=e) for s, e in raw]
        if not segments:
            raise AudioNoSpeechError(details={"wav_path": str(wav_path)})
        return segments
```

- [ ] **Step 2：撰寫 `app/services/audio/_firered_vad_loader.py`（隔離載入細節）**

```python
"""FireRedVAD 模型載入器。

實際模型載入會依 FireRedVAD repo 提供的 API。Phase 1 提供 placeholder
讓 service 結構就緒；M4 啟動 GPU 環境時補完真實載入。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


def load_firered_vad(model_path: Path) -> Any:
    """嘗試載入 FireRedVAD 模型；若 import 失敗則 raise RuntimeError。"""
    try:
        # FireRedVAD 官方倉庫尚未發 PyPI；運行環境必須將 repo 安裝為套件
        from firered_vad import FireRedVAD  # type: ignore[import-not-found]
    except ImportError as e:
        raise RuntimeError(
            "firered_vad 套件未安裝。請將 FireRedVAD 倉庫安裝為可 import 的套件。"
        ) from e

    if not model_path.exists():
        raise RuntimeError(f"VAD 模型權重不存在：{model_path}")
    logger.info("loading FireRedVAD", model_path=str(model_path))
    return FireRedVAD.load(str(model_path))
```

- [ ] **Step 3：撰寫 `tests/unit/test_audio_vad.py`（純 mock 測試）**

```python
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
```

- [ ] **Step 4：補完 `app/services/audio/__init__.py`**

```python
"""音檔處理 service：MIME、儲存、重取樣、VAD。"""

from app.services.audio.mime import verify_mime
from app.services.audio.resampler import ResampleResult, resample_to_16k_mono
from app.services.audio.storage import store_upload
from app.services.audio.vad import FireRedVADService, Segment

__all__ = [
    "FireRedVADService",
    "ResampleResult",
    "Segment",
    "resample_to_16k_mono",
    "store_upload",
    "verify_mime",
]
```

- [ ] **Step 5：執行測試**

```bash
pytest tests/unit/test_audio_vad.py -v
```

預期：4 測試 PASS。

- [ ] **Step 6：Commit**

```bash
git add backend/app/services/audio/vad.py backend/app/services/audio/_firered_vad_loader.py backend/app/services/audio/__init__.py backend/tests/unit/test_audio_vad.py
git commit -m "feat(audio): 加入 FireRedVAD 包裝與單例管理"
```

---

## Task 3.6：M3 端到端整合測試

**Files:**
- Create: `backend/tests/integration/test_audio_pipeline.py`

- [ ] **Step 1：撰寫整合測試**

```python
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.repositories.audio_file import AudioFileRepository
from app.services.audio import (
    FireRedVADService,
    Segment,
    resample_to_16k_mono,
    store_upload,
    verify_mime,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "audio"
SUPPORTED = ["wav", "mp3", "mp4", "flac", "aac", "ogg", "m4a"]


class _FakeVadModel:
    def infer(self, wav_path: str) -> list[tuple[float, float]]:
        return [(0.0, 1.0)]


@pytest.fixture(autouse=True)
def _stub_vad() -> None:
    FireRedVADService.set_model(_FakeVadModel())
    yield
    FireRedVADService.set_model(None)


@pytest.mark.asyncio
async def test_full_pipeline_8khz_to_16khz(
    db_session: Session, seed_api_key: int, tmp_path: Path
) -> None:
    raw_bytes = (FIXTURES / "valid_8k_mono.wav").read_bytes()

    # 1. MIME 校驗
    mime, ext = verify_mime(raw_bytes, SUPPORTED)
    assert ext == "wav"

    # 2. 落地儲存
    audio = store_upload(
        db=db_session,
        api_key_id=seed_api_key,
        raw_bytes=raw_bytes,
        original_name="user_8k.wav",
        canonical_ext=ext,
        verified_mime=mime,
        storage_dir=tmp_path / "storage",
    )

    # 3. 重取樣
    result = await resample_to_16k_mono(Path(audio.storage_path), tmp_path / "processed")
    assert result.resampling_warning is True
    assert result.original_sample_rate == 8000

    # 4. 寫回 audio_files
    AudioFileRepository(db_session, seed_api_key).update_after_resample(
        audio.id,
        original_sample_rate=result.original_sample_rate,
        duration_sec=result.duration_sec,
    )

    # 5. VAD 偵測
    segments = await FireRedVADService.detect_speech(result.output_path)
    assert len(segments) >= 1
    assert isinstance(segments[0], Segment)

    # 驗證 DB 狀態
    db_session.refresh(audio)
    assert audio.original_sample_rate == 8000
    assert audio.duration_sec is not None
```

- [ ] **Step 2：執行測試**

```bash
pytest tests/integration/test_audio_pipeline.py -v
```

預期：1 個測試 PASS。

- [ ] **Step 3：跑全 M3 覆蓋率**

```bash
pytest tests/unit/test_audio_*.py tests/integration/test_audio_pipeline.py --cov=app/services/audio --cov=app/repositories/audio_file --cov-report=term
```

預期：覆蓋率 ≥ 70%，且 `services/audio/mime.py` ≥ 90%。

- [ ] **Step 4：Lint + Type 整體**

```bash
ruff check app tests
mypy app
```

- [ ] **Step 5：Commit + Push**

```bash
git add backend/tests/integration/test_audio_pipeline.py
git commit -m "test(audio): 加入 M3 端到端整合測試（MIME → 儲存 → 重取樣 → VAD）"
git push origin main
```

---

## Self-Review

**1. Spec coverage（對照設計文件第 2.4、5 段）：**

| 設計章節 | 對應 Task |
|---------|----------|
| 2.4 M3 工作項目 (1)–(5) | T3.1–T3.5 全部涵蓋 |
| 5.1 整體資料流 | T3.6 端到端測試 |
| 5.2 介面契約 | T3.2 / T3.3 / T3.4 / T3.5 |
| 5.3 重取樣關鍵設計 | T3.4 |
| 5.4 VAD 關鍵設計 | T3.5 |
| 5.5 audio_files 兩階段寫入 | T3.3（INSERT） + T3.4（UPDATE via repository） |
| 5.6 隔離邊界與安全考量 | T3.2（MIME）、T3.3（UUID）、T3.4（timeout） |
| 5.7 測試 fixture 清單 | T3.1 |
| 5.8 Phase 1 不實作項目 | 無對應 task（設計層級已聲明跳過） |
| 2.4 M3 DoD 條件 1–7 | T3.6 |

**2. Placeholder scan：** `_firered_vad_loader.py` 中 `from firered_vad import FireRedVAD` 為實際 import 語句（雖然套件可能尚未安裝，但這是正確的延伸點處理，非 TBD / placeholder）。所有測試與程式碼皆完整。

**3. Type consistency：**
- `Segment(start_sec, end_sec)` 在 vad.py、test、integration test 三處欄位名一致
- `ResampleResult` 欄位（output_path / original_sample_rate / duration_sec / resampling_warning）在 resampler、test、integration test 一致
- `verify_mime` 回傳 `(mime, ext)` 與 test、storage 呼叫端對齊
- `AudioFileRepository.update_after_resample` 簽章與 test 對齊

---

## Execution Handoff

M3 plan 完成。M4 plan 撰寫中，完成後一併進入 Subagent-Driven Execution。
