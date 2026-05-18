#!/usr/bin/env bash
# 容器啟動入口：先把資料庫升到最新 schema 再啟動 FastAPI。
#
# 設計考量：
# 1. 在 entrypoint 跑 `alembic upgrade head` 而非 lifespan startup —— 失敗時容器直接 exit
#    非零，docker compose `restart: unless-stopped` 會 restart loop，operator 可從容器 log
#    看到實際錯誤；若放 lifespan，部分模組（vLLM、pyannote）已先載入幾 GB VRAM 才崩，
#    回收成本高。
# 2. exec "$@"：tini 為 PID 1，entrypoint.sh 不能是長駐 process —— exec 把 PID 1 從本
#    腳本轉移給 CMD（uvicorn），確保 SIGTERM / SIGINT 等信號被正確 forward。
# 3. depends_on: postgres condition: service_healthy 已保證 alembic 跑時 DB 就緒，
#    此處不額外做 retry / wait-for-it。
set -euo pipefail

cd /app

echo "[entrypoint] running alembic upgrade head"
alembic upgrade head

echo "[entrypoint] migrations complete; exec into CMD"
exec "$@"
