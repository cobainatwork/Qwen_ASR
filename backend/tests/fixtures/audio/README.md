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
