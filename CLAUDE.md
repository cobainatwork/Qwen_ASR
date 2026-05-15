# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 專案狀態（重要前提）

本倉庫處於**設計規格階段**，截至本檔建立時：

- 沒有任何後端、前端程式碼。`backend/`、`frontend/`、`docker-compose.yml`、`.env.example` 皆尚未建立。
- `master` 分支從未有過 commit，亦未設定 remote。
- 所有實作決策必須回溯規格書與審查報告，不可憑空產生程式架構。

實作開始後，再依本檔最後一節「開發指令（實作後補齊）」更新 build/lint/test 命令。

## 必讀文件（依優先順序）

進入本專案任何任務前，先讀過下列檔案。它們互相補充，缺一不可：

1. `docs/superpowers/specs/2026-05-11-qwen3-asr-platform-design.md`（**v1.9**）— **唯一權威設計規格**。所有 API、資料表、Docker 配置、安全機制皆以此為準。包含完整 changelog、附錄 A 錯誤碼字典、22-26 節（可觀測性、SLO、DR、合規、授權）。
2. `multi-angle-review-report.md` — v1.4 多角度審查的 87 項發現，**18 項 P0 已於 v1.9 全數修正**，保留為歷史脈絡。
3. `spec-review-report.md` — v1.1 初審報告，已修正項目（B-1、A-5、E-1、C-5），保留為歷史脈絡。

規格書內容變動頻繁時，以規格書 > 多角度審查 > 初審報告的順序判定。

## 技術棧

| 層 | 技術 |
|----|------|
| 後端 | Python 3.12、FastAPI + Uvicorn、SQLAlchemy ORM |
| 前端 | Next.js 14（App Router）、React 18、TypeScript、Tailwind CSS |
| 資料庫 | PostgreSQL 16（含 zhparser 中文全文檢索擴充） |
| 容器化 | Docker Compose |
| GPU | NVIDIA GPU 48 GB VRAM + NVIDIA Container Toolkit |
| ASR 模型 | Qwen3-ASR-1.7B（主力）+ Qwen3-ASR-0.6B（備用） |
| 對齊模型 | Qwen3-ForcedAligner-0.6B |
| VAD | FireRedVAD（0.6M 參數） |
| 語者分離 | pyannote.audio（主）+ CAM++（備用，Fine-tune 期間強制降級） |
| 語音增強 | ClearVoice（可選） |
| 命名實體糾錯 | Generative-Annotation-NEC（可選） |
| 音檔下載 | yt-dlp（YouTube） |
| 音檔重取樣 | torchaudio / soxr |

詳細目錄結構與模組設計參閱規格書「三、後端服務設計」與「四、前端介面設計」。

## 跨檔案架構決策（讀單一檔案無法理解的部分）

### 推理引擎：vLLM AsyncLLMEngine 強制取代多行程

- 規格書 3.1、3.3.1 節要求**廢除 `ProcessPoolExecutor`**。FastAPI 啟動時直接初始化 `AsyncLLMEngine`，路由內 `await engine.generate()`。
- 任何時候看到「啟動 worker 子行程」「ProcessPool」的程式雛形，皆屬規格不符。

### 單端口（HTTP + WebSocket 共用 8000）與 `workers=1`

- 規格書 3.1、3.3.7、7.2 節：Uvicorn **必須**設定 `workers=1`。原因：WS 連線會綁定到特定 worker，多 worker 會破壞連線管理。
- 不可為了「效能」改成多 worker；水平擴展屬 V2 範圍（Redis + 獨立 Worker 實例）。

### 處理管線順序（已修正）

規格書 6.1 節最終順序為：

```
重取樣 → 可選降噪 → VAD → ASR 推理 → ForcedAligner 對齊 → 語者分離 → 後處理
```

審查報告 P0-BE-2 修正前的「VAD → 降噪」順序錯誤，禁止沿用。降噪先於 VAD 才能維持 FireRedVAD F1 97.57% 的指標。

### 切段限制與佇列抽象層

- ASR 支援單檔 20 分鐘；ForcedAligner 限 5 分鐘（規格書 3.3.1 節）。長音檔分階段切段，不可一律以 5 分鐘切。
- V1 即定義 `QueueBackend` 抽象介面（`enqueue/dequeue/cancel/status/size`），V1 實作 `AsyncioQueueBackend`、V2 擴展 `RedisQueueBackend`。業務邏輯禁止直接操作 `asyncio.Queue`。

### VRAM 預算（48 GB GPU）與 Fine-tune 隔離

- 必載 ~6.6 GB（ASR 1.7B 4 GB + Aligner 0.6B 2 GB + VAD 0.1 GB）。
- 按需載入：pyannote、ClearVoice、NEC、Qwen2.5-7B INT4（4.5 GB）。
- Fine-tune 進行時必須執行：
  1. 推理 `batch_size = 1`。
  2. `torch.cuda.set_per_process_memory_fraction(0.65)` 限制訓練程序至 31 GB。
  3. pyannote **強制降級為 CAM++（純 CPU）**。
  4. 剩餘 VRAM < 8 GB 時暫停 Fine-tune。

詳見規格書 18.2 節。任何涉及推理或訓練的 PR，必須在說明中標註 VRAM 影響。

### 雙模型交替策略（Zero-downtime 模型切換）

- `POST /api/asr/switch-model` 時，新模型載入至 standby 槽位，原子性切換 active 指標，舊模型在無進行中任務時才 unload。
- 進行中的任務綁定到當時的模型版本，`transcriptions` 表 `model_version` 欄位記錄。
- 直接 unload 後再 load 是錯誤實作（會中斷進行中的推理，違反 P0-BE-1）。

### Hotword 三層架構與糾錯四層管線

- Hotword 規模 < 100 用 Shallow Fusion；100–1000 用 CTC-WS；> 1000 進入 Fine-tune（規格書 13 節）。實作 hotword 服務時必須先讀詞數判斷層級。
- 糾錯順序：NEC → KenLM → 同音異字 → LLM（規格書 16 節）。每層可選，失敗時跳過並寫入 `post_processing` JSONB，**不可拋出例外中斷整個辨識**。

### 部署 Profile（Client vs Vendor）

- **Client Profile（甲方）**：僅啟用 ASR 推理、WS、歷史紀錄、Hotword。Fine-tune 與校正工作台必須以環境變數硬性關閉。
- **Vendor Profile（乙方代管）**：全模組啟用，調降 `VLLM_GPU_MEMORY_UTILIZATION` 以與 `torchrun` 訓練共存。

新增模組時必須回答：屬於哪個 profile？由哪個環境變數控制啟用？

## 強制規範（不可違反）

### API 層

1. **路徑前綴**：所有 REST API 必須位於 `/api/v1/` 之下（規格書 3.6.1 節）。Breaking change 要求建立 `/api/v2/`，舊版本至少維運 6 個月並加 `Sunset` header。
2. **統一回應結構**：所有 REST API 必須以 `{success, data, error}` 包裝（規格書 3.6 節）。`success: true` 時 `data` 必填、`error: null`；非 2xx 時 `success: false`、`data: null`、`error: {code, message}`。**禁止自行發明欄位**。錯誤碼必須使用附錄 A 字典定義。
3. **標準分頁結構**：列表 API 一律 `data: {items: [...], pagination: {total, page, limit, total_pages}}`，欄位名不可變動。大型資料集改用 cursor-based 分頁。
4. **列表 API 大欄位排除**：列表回應預設排除 `timestamps`、`speakers`、`post_processing`、`asr_result`、`loss_history`、`original_text`、`corrected_text` 等 JSONB/TEXT 大欄位；完整內容透過詳情 API 取得。
5. **多租戶隔離（Tenant Isolation）**：透過 `get_current_tenant` FastAPI Dependency 取得 `api_key_id`。Repository 層**自動掛載** `api_key_id` 過濾，禁止業務程式碼手動拼接 `WHERE api_key_id = X`。涉及 `transcriptions / audio_files / correction_sessions / finetune_tasks / hotword_groups / hotwords / correction_segments / datasets / finetune_checkpoints / youtube_downloads` 的查詢皆適用。
6. **Bearer Token + Scope 認證**：所有端點必須驗證 `Authorization: Bearer <api_key>`。**僅 `GET /health` 與 `GET /readiness` 豁免**。Token 以 Argon2id（`time_cost=3, memory_cost=65536, parallelism=4`）雜湊儲存於 `api_keys.key_hash`。每個端點以 `Depends(require_scope("<scope>"))` 強制宣告所需 scope。
7. **冪等性**：建立資源型端點（POST `/transcribe`、`/upload/init`、`/finetune/upload`、`/finetune/tasks`、`/dataset/youtube/download`、`/hotword/groups`）必須支援 `Idempotency-Key` header，24 小時 TTL。

### 音檔上傳

8. **MIME 實際校驗**：使用 `python-magic`（libmagic）以 magic bytes 偵測，**不可依賴副檔名**。白名單僅 `audio/*` 與 `video/*`。
9. **檔名重寫**：上傳檔以 UUID v4 重新命名儲存，避免路徑穿越與覆蓋。原始檔名僅作為顯示用途。
10. **預處理輸出**：進入 ASR 管線前必為 16kHz mono WAV。8kHz 音檔需重取樣，並在 `transcriptions` 記錄 `resampling_warning`（規格書 12 節）。
11. **大檔分片**：大於 `CHUNKED_UPLOAD_THRESHOLD_MB`（預設 100 MB）的音檔必須使用 `/api/v1/asr/upload/init` → `chunk` → `complete` 流程，每片獨立 SHA256 驗證。

### WebSocket

12. **認證**：透過 `Sec-WebSocket-Protocol: asr.v1, bearer.<base64url(token)>`。**禁止透過 query string 傳遞 token**（會被 access log / Referer 洩漏）。連線時驗證 scope（`/ws/quality` 需 `asr:write`）。
13. **心跳協議**：前端每 30 秒送 `{"action": "ping"}`；後端立刻回 `{"action": "pong", "timestamp": ...}`。後端超過 90 秒未收 ping 必須主動斷線（規格書 3.3.7 節）。
14. **訊息上限**：`WS_MAX_MESSAGE_SIZE_MB` 預設 50；單金鑰最大連線數 `WS_MAX_CONNECTIONS_PER_KEY` 預設 10。

### 資料模型

15. **時區**：所有 `TIMESTAMP` 欄位使用 `TIMESTAMP WITH TIME ZONE`，UTC 儲存，應用層依使用者時區呈現。
16. **Optimistic Locking**：`correction_segments` 等多人編輯資源必須以 `version` 欄位實作 optimistic locking，PUT 時提供 `expected_version`，不符回 409 `CORRECTION_VERSION_MISMATCH`。
17. **軟刪除**：`api_keys` 刪除為軟刪除（寫入 `deleted_at`）；徹底刪除（含關聯資料）必須透過 `/api/v1/auth/keys/:id/erase` 並寫入 `audit_logs`。

### 文件與程式碼

18. **語言**：規格書全文繁體中文。程式碼註解、commit 訊息、README、API 錯誤訊息建議維持繁體中文。
19. **Fine-tune 並發**：同一時間僅允許 1 個訓練任務（`FINETUNE_MAX_CONCURRENT=1`）。
20. **可觀測性**：所有 log 為 JSON Lines，必含 `trace_id / request_id / api_key_id / endpoint / duration_ms / error_code`；**禁止**寫入 token、音檔 base64、辨識結果、原始檔名。
21. **第三方授權**：啟動時檢查 `THIRD_PARTY_LICENSE_ACK=true`，未設定則拒絕啟動。

## 環境特異性

- **開發環境**：Windows + Docker Desktop。Windows 對 NVIDIA GPU 支援有限（僅 WSL2 部分支援），**後端 GPU 服務不在 Windows 直接跑**；Windows 僅用於前端、資料庫、純 CPU 邏輯開發。
- **部署環境**：Linux + NVIDIA GPU 48 GB VRAM + NVIDIA Container Toolkit。
- 涉及 Linux-only 路徑（如 LUKS 加密、`/data/*` 掛載點）的程式碼，必須在 Windows 端提供 fallback 或 skip 機制。

## 規格凍結狀態（v1.9）

v1.4 多角度審查 18 項 P0 已於 v1.9 全數修正，並追加 30+ 項既有審查未涵蓋的補強。

### v1.1 初審修正（spec-review-report.md）

| 編號 | 內容 |
|------|------|
| P0 B-1 | 修正切段邏輯：ASR 20 分鐘、ForcedAligner 5 分鐘 |
| P0 A-5 | 補齊 ASR / 歷史 / 模型 REST API 端點表格 |
| P0 E-1 | 增加 API 認證機制設計 |
| P0 C-5 | 釐清 WS 雙端口 vs 單端口方案（採單端口） |

### v1.4 多角度審查矩陣（multi-angle-review-report.md）

| 角度 | P0 | P1 | P2 | P3 | 小計 | v1.9 狀態 |
|------|----|----|----|----|------|----------|
| 後端架構 | 3 | 7 | 6 | 2 | 18 | 全數已修正 |
| 資安 | 4 | 5 | 5 | 3 | 17 | 全數已修正 |
| ML 工程 | 3 | 6 | 5 | 1 | 15 | 全數已修正 |
| 前端開發 | 4 | 5 | 6 | 2 | 17 | 全數已修正 |
| Docker / DevOps | 4 | 8 | 8 | 0 | 20 | 全數已修正 |
| **總計** | **18** | **31** | **30** | **8** | **87** | 全數已修正 |

### v1.9 追加補強（30+ 項既有審查未涵蓋）

- **內部一致性：** `BACKEND_TYPE` 矛盾、`DISCLEANUP_SCHEDULE` 拼字、表格缺 `api_key_id`、Fine-tune 學習率異常。
- **認證強化：** API scopes（10 種）、WebSocket subprotocol 認證、軟刪除、`audit_logs`。
- **全新章節：** 22 可觀測性、23 SLO / SLA、24 災難復原、25 個資合規、26 第三方授權、附錄 A 錯誤碼字典。
- **API 設計：** `/api/v1/` 前綴、`Idempotency-Key`、cursor 分頁、批次辨識、分片上傳。
- **資料表：** `datasets`、`finetune_checkpoints`、`chunked_uploads`、`audit_logs`、optimistic locking。
- **運維強化：** 雙通道佇列（realtime / batch）、GPU 故障處理、模型 fallback 決策表、zhparser 全文檢索、SHA256 模型驗證。
- **資安強化：** Sliding Window 限流、CSP、安全標頭、OpenAPI 文檔處置。
- **CI / CD：** 13 階段檢查（migration、API contract、E2E、授權審計、secret 掃描）。

可直接進入實作階段。任何發現的規格瑕疵都應先提 PR 修正規格書再寫程式。

## 跨領域風險（觸碰相關模組時務必警覺）

- **VRAM 計算不完整**（ML-02、ML-03、P1-BE-4、SEC-08、P1-DEVOPS-6）— 任何新增模型或推理路徑都要重算 VRAM。
- **Fine-tune 與推理資源衝突**（ML-01、ML-02、P1-BE-2、SEC-08）— Fine-tune 啟動程式碼必須觸發推理降級。
- **yt-dlp SSRF**（SEC-03）— `/api/dataset/youtube/download` 必須有網域白名單與協議限制（僅 https）。
- **資料無加密**（SEC-04）— 短期 LUKS、中期 AES-256-GCM 欄位級加密，金鑰由 `ENCRYPTION_KEY` 注入。
- **Docker 映像過大**（P0-DEVOPS-2、ML-10）— 後端三階段建構強制，模型權重透過 volume 掛載而非打包。

## 實作順序建議

1. 建立 `.gitignore`、`docker-compose.yml`、`.env.example`。
2. 後端基礎架構（FastAPI 入口、SQLAlchemy 模型、Alembic 遷移）。
3. 音檔預處理管線（取樣率自適應 + VAD）。
4. ASR 推理引擎（vLLM AsyncLLMEngine）。
5. REST API 端點（含 Hotword、Dataset）。
6. 前端 scaffolding（Next.js 14 App Router）。
7. 語者分離、後處理、糾錯管線。
8. Fine-tune 管線（含資料增強、品質評估）。
9. YouTube 下載 + 校正工作台。
10. WebSocket 質檢接口。
11. 健康檢查、Prometheus 監控、安全控管。

## 環境變數速查（必填與常用切換項）

完整清單參閱規格書「十、環境變數配置」，下表為啟動時必填或常用切換項：

| 變數 | 預設值 | 必填 | 說明 |
|------|--------|------|------|
| `API_KEY` | — | 是 | Bootstrap admin 金鑰 |
| `DATABASE_URL` | — | 是 | PostgreSQL 連線字串 |
| `DB_PASSWORD` | — | 是 | 資料庫密碼 |
| `THIRD_PARTY_LICENSE_ACK` | `false` | 是 | 未設 `true` 拒絕啟動 |
| `ENV` | `development` | 是 | 部署環境識別 |
| `DEPLOYMENT_PROFILE` | `client` | 是 | `client` 或 `vendor` |
| `HF_TOKEN` | — | 條件式 | 啟用 pyannote 時必需 |
| `ENCRYPTION_KEY` | — | 條件式 | 啟用欄位級加密時必需 |
| `ASR_MODEL` | `Qwen/Qwen3-ASR-1.7B` | 否 | 主力 ASR 模型 |
| `BACKEND_TYPE` | `vllm` | 否 | 強制 `vllm` |
| `VAD_ENABLED` | `true` | 否 | VAD 開關 |
| `DIARIZATION_ENABLED` | `true` | 否 | 語者分離開關 |
| `POST_PROCESSING_ENABLED` | `true` | 否 | 後處理開關 |
| `DATA_AUGMENTATION_ENABLED` | `false` | 否 | 資料增強開關 |
| `CORRECTION_KENLM_ENABLED` | `false` | 否 | KenLM 糾錯開關 |
| `FINETUNE_MAX_CONCURRENT` | `1` | 否 | Fine-tune 並發上限（強制 1） |
| `CHUNKED_UPLOAD_THRESHOLD_MB` | `100` | 否 | 觸發分片上傳的檔案大小 |
| `AUDIO_RETENTION_DAYS` | `30` | 否 | 音檔保留天數 |
| `WS_MAX_MESSAGE_SIZE_MB` | `50` | 否 | WS 單訊息上限 |
| `WS_MAX_CONNECTIONS_PER_KEY` | `10` | 否 | 單金鑰 WS 連線上限 |

## 開發指令（實作後補齊）

目前尚無任何 build/lint/test 指令。實作後請更新本節並維持下列結構：

```
# 後端開發
backend $ uvicorn app.main:app --reload --port 8000
backend $ pytest [-k <test_name>]
backend $ ruff check . && mypy .
backend $ alembic upgrade head

# 前端開發
frontend $ npm run dev
frontend $ npm run test [-- <pattern>]
frontend $ npm run lint && npm run typecheck

# 整合
$ docker compose up -d
$ docker compose logs -f asr-backend
```

實際指令以實作時的 `package.json` / `pyproject.toml` 為準。
