#!/usr/bin/env bash
# Linux + NVIDIA GPU 環境執行的 ASR 端到端 manual smoke。
# 使用方式：
#   export ASR_SMOKE_TOKEN="<bootstrap API key>"
#   export ASR_SMOKE_HOST="http://localhost:8000"
#   ./scripts/smoke_asr.sh tests/fixtures/audio/valid_16k_mono.wav
#   ./scripts/smoke_asr.sh /path/to/conversation.wav --require-diarization
#
# --require-diarization：當 response.data.diarization.status != "ok" 或 speakers_count == 0
#                        時 exit 1。需要真正多人對話音檔（valid_16k_mono.wav 是 440 Hz
#                        正弦波，pyannote 不會偵測為 speech）。
set -euo pipefail

HOST="${ASR_SMOKE_HOST:-http://localhost:8000}"
TOKEN="${ASR_SMOKE_TOKEN:?need bootstrap admin token}"
AUDIO_FILE="${1:?usage: $0 <audio_path> [--require-diarization]}"
REQUIRE_DIARIZATION="${2:-}"

if [ ! -f "$AUDIO_FILE" ]; then
  echo "audio file not found: $AUDIO_FILE" >&2
  exit 2
fi

echo "smoke: POST $HOST/api/v1/asr/transcribe with $AUDIO_FILE"
# qwen-asr 0.0.6 僅接英文官方語言名稱（Chinese / English / Cantonese ...），不接受 ISO 代碼。
response=$(curl -fsS -X POST "$HOST/api/v1/asr/transcribe" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@$AUDIO_FILE" \
  -F 'options_json={"language":"Chinese","return_timestamps":true}')

echo "$response" | jq '{
  success,
  text: .data.text,
  duration_sec: .data.duration_sec,
  processing_duration_sec: .data.processing_duration_sec,
  model_version: .data.model_version,
  resampling_warning: .data.resampling_warning,
  vad_segments_count: .data.vad_segments_count,
  diarization: .data.diarization,
  speakers_count: (.data.speakers | length),
  warnings: .data.warnings
}'

success=$(echo "$response" | jq -r '.success')
if [ "$success" != "true" ]; then
  echo "smoke failed: $response" >&2
  exit 1
fi

if [ "$REQUIRE_DIARIZATION" = "--require-diarization" ]; then
  status=$(echo "$response" | jq -r '.data.diarization.status // "null"')
  speakers_count=$(echo "$response" | jq -r '.data.speakers | length // 0')
  if [ "$status" != "ok" ] || [ "$speakers_count" -eq 0 ]; then
    echo "diarization assertion failed: status=$status speakers_count=$speakers_count" >&2
    exit 3
  fi
  echo "diarization OK: speakers_count=$speakers_count"
fi

echo "smoke OK"
