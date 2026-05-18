#!/usr/bin/env bash
# Linux + NVIDIA GPU 環境執行的 ASR 端到端 manual smoke。
# 使用方式：
#   export ASR_SMOKE_TOKEN="<bootstrap API key>"
#   export ASR_SMOKE_HOST="http://localhost:8000"
#   ./scripts/smoke_asr.sh tests/fixtures/audio/valid_16k_mono.wav
set -euo pipefail

HOST="${ASR_SMOKE_HOST:-http://localhost:8000}"
TOKEN="${ASR_SMOKE_TOKEN:?need bootstrap admin token}"
AUDIO_FILE="${1:?usage: $0 <audio_path>}"

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
  warnings: .data.warnings
}'

success=$(echo "$response" | jq -r '.success')
if [ "$success" != "true" ]; then
  echo "smoke failed: $response" >&2
  exit 1
fi
echo "smoke OK"
