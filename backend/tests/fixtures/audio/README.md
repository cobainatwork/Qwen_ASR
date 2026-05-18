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

## diarization 端到端 smoke

`smoke_asr.sh --require-diarization` 需要**真正多人對話音檔**：上列 fixture 全為合成正弦波或靜音，pyannote 不會偵測為 speech。Linux GPU 環境執行時請另行準備（例如 LibriVox/CommonVoice CC 授權片段或自錄雙人對話）：

    ./scripts/smoke_asr.sh /path/to/conversation_16k.wav --require-diarization

assertion 通過條件：`response.data.diarization.status == "ok"` 且 `speakers` 至少一段。
