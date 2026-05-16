# Phase 2 / M5-M11 Implementation Design

> **本文目的**：在規格書 v1.9 凍結基礎上，整理 Phase 2 七個 milestone 的「實作策略」（非規格設計）。所有架構、API、Schema、安全機制以規格書為唯一權威；本 design 僅釐清跨檔案決策、模組職責邊界、執行順序與品質基準。
>
> **規格基準**：`docs/superpowers/specs/2026-05-11-qwen3-asr-platform-design.md` v1.9
>
> **撰寫日期**：2026-05-16

---

## 一、釐清決策摘要

### 1.1 範圍

Phase 2 涵蓋 7 個 milestone，對應 `CLAUDE.md` 實作順序 5-11：

| Milestone | 對應實作順序 | Profile |
|-----------|------------|---------|
| M5 REST API 端點（Hotword + Dataset） | 5 | Client + Vendor |
| M6 前端 scaffolding | 6 | Client + Vendor |
| M7 ForcedAligner + 語者分離 + 後處理 + 糾錯管線 | 7 | **Vendor only** |
| M8 Fine-tune 管線 | 8 | **Vendor only** |
| M9 YouTube 下載 + 校正工作台 | 9 | **Vendor only** |
| M10 WebSocket 質檢接口 | 10 | Client + Vendor |
| M11 健康檢查 / Prometheus / 安全控管 | 11 | Client + Vendor |

### 1.2 與 Phase 1 的關係

Phase 1（M1-M4）已建立基礎骨架：FastAPI + DB + 認證 + 預處理 + ASR 推理 + transcribe 端點。Phase 2 在此之上擴展功能模組，**不修改 M1-M4 的核心契約**（ResponseEnvelope、TenantScopedRepository、AppException 子類別、middleware 順序、lifespan 結構）。

### 1.3 程式碼品質基準（clean-code 約束）

所有 Phase 2 plan 中提供的 Python / TypeScript code snippet 必須遵守：

- **函式長度** < 20 行（Single Level of Abstraction）
- **單一職責**（Do One Thing）
- **命名 intention-revealing**（`elapsed_resample_ms` 而非 `t`）
- **參數 ≤ 2**（複雜情境用 dataclass / Pydantic model 包裝）
- **無副作用**（純函式優先；side-effect 集中在 service 層）
- **拒絕 null 流通**（Optional 在邊界處理，不深入內部邏輯）
- **錯誤處理走 AppException** 子類別（M2 T2.2 既有 20 個 + Phase 2 擴充）

CI 透過 `ruff` + `mypy strict` 檢查；不通過則拒絕合併。

### 1.4 規格瑕疵處理約定（沿用 Phase 1）

- Plan 中發現 bug 或不可攜語法 → 先在 plan 中標註修正（PHASE2-SPEC-XX）→ implementation 階段修補 → 後續發 docs PR 修規格書
- 程式碼品質 reviewer 找出的可優化項記為 PHASE2-OPT-XX，集中於 milestone 之間處理

---

## 二、整體架構與目錄骨架

### 2.1 既有結構（M1-M4 不動）

```
backend/
  app/
    core/         # config / exceptions / response / logging / security / startup_checks
    deps/         # db / auth
    middleware/   # request_id / error_handler / 4 個 no-op
    models/       # ApiKey / AudioFile / Transcription / AuditLog
    repositories/ # TenantScopedRepository[T] + 具體 repo
    routers/      # health / asr
    schemas/      # common / asr
    services/
      audio/      # mime / storage / resampler / vad
      asr/        # queue / engine / transcriber / consumer
    main.py
  alembic/        # versions/0001_phase1_initial.py
  tests/          # unit / integration / fixtures
```

### 2.2 Phase 2 新增目錄

| Milestone | 新增路徑 | 責任 |
|-----------|---------|------|
| M5 | `app/routers/hotword.py` | Hotword group / 詞彙 CRUD |
| M5 | `app/routers/dataset.py` | Dataset CRUD |
| M5 | `app/services/hotword/` | 三層架構決策器、CTC-WS 整合 |
| M5 | `app/services/dataset/` | Dataset 建立、樣本驗證 |
| M5 | `app/repositories/hotword.py` / `dataset.py` | 對應 repo |
| M5 | `app/schemas/hotword.py` / `dataset.py` | Pydantic schema |
| M5 | `app/models/hotword.py` / `dataset.py` | ORM model |
| M6 | `frontend/` | Next.js 14 全新建立 |
| M7 | `app/services/aligner/` | ForcedAligner 載入與 5 分鐘切段 |
| M7 | `app/services/diarization/` | pyannote + CAM++ wrapper |
| M7 | `app/services/post_processing/` | 標點、數字正規化、英文處理 |
| M7 | `app/services/correction/` | NEC / KenLM / 同音 / LLM 四層 |
| M8 | `app/services/finetune/` | torchrun runner、狀態機 |
| M8 | `app/services/dataset_augmentation/` | 資料增強策略 |
| M8 | `app/routers/finetune.py` | Finetune CRUD |
| M8 | `app/repositories/finetune.py` | Finetune task / checkpoint repo |
| M8 | `app/models/finetune.py` | finetune_tasks / finetune_checkpoints ORM |
| M8 | `backend/scripts/finetune_runner.py` | 訓練主程式 |
| M9 | `app/services/youtube/` | yt-dlp 包裝、SSRF 防護 |
| M9 | `app/routers/youtube.py` | YouTube 下載端點 |
| M9 | `app/routers/correction.py` | 校正工作台端點 |
| M9 | `app/models/correction.py` / `youtube.py` | ORM |
| M9 | `frontend/app/correction/` | 校正 UI |
| M10 | `app/routers/ws.py` | `/ws/quality` 端點 |
| M10 | `app/services/ws_quality/` | WS connection manager / 心跳 |
| M11 | `app/middleware/prometheus_active.py` | 取代 no-op（保留 plan T2.10 no-op 為 fallback） |
| M11 | `app/middleware/tracing_active.py` / `rate_limit_active.py` | 同上 |
| M11 | `app/routers/metrics.py` | `GET /metrics` Prometheus exposition |
| M11 | `app/routers/auth_admin.py` | `/auth/keys/:id/erase` 等管理端點 |

### 2.3 Frontend 目錄骨架（M6）

```
frontend/
  app/                  # Next.js 14 App Router
    page.tsx            # 首頁辨識
    history/page.tsx    # 歷史紀錄
    keys/page.tsx       # API 金鑰
    correction/         # M9 加入
  components/
    ui/                 # Tailwind + Apple Glassmorphism 基底元件
    layout/             # Header / Sidebar
    asr/                # 辨識相關
  lib/
    api/                # typed API client（從 OpenAPI 生成）
    auth/               # Bearer token 管理
  styles/
    globals.css
  tests/
    unit/               # Jest + React Testing Library
    e2e/                # Playwright（M9+ 啟用）
```

---

## 三、七個 Milestone 子模組切分與 DoD

### 3.1 M5：REST API 端點（Hotword + Dataset）

**範圍**：依規格 §3.4、§13 實作 Hotword 三層架構與 Dataset 管理 API。

**關鍵元件**：

1. **Hotword 三層分流決策器**（規格 §13.2）：
   - `< 100` 詞 → Shallow Fusion（推理時 logits 加權）
   - `100-1000` 詞 → CTC-WS（CTC Word Spotter）
   - `> 1000` 詞 → 拒絕直接 Hotword，提示啟動 Fine-tune（M8 對接）
2. **Dataset 樣本驗證**：上傳音檔 + 標註 → MIME 校驗（複用 M3）→ 16 kHz 重取樣 → 入 `datasets` 表

**API 端點**（規格 §3.4）：
- `POST /api/v1/hotword/groups` 建立群組
- `GET /api/v1/hotword/groups` 列表
- `GET /api/v1/hotword/groups/:id` 詳情
- `PUT /api/v1/hotword/groups/:id` 更新
- `DELETE /api/v1/hotword/groups/:id` 軟刪除
- `POST /api/v1/hotword/groups/:id/words/bulk` 批次上傳詞彙
- `POST /api/v1/dataset` 建立
- `GET /api/v1/dataset` 列表
- `POST /api/v1/dataset/:id/samples` 新增樣本
- `GET /api/v1/dataset/:id/samples` 列出樣本

**DoD**：
- 10 個端點 PASS（含 Tenant Isolation 驗證）
- Hotword 規模分流邏輯三組 case 都正確
- 規格 §13.4 三層架構切換閾值可由 ENV 覆寫
- 累積測試 ≥ 130（M4 106 + 24+）

**依賴**：
- M2 既有 TenantScopedRepository、認證、ResponseEnvelope
- M3 既有 verify_mime、store_upload、resample_to_16k_mono
- M4 暫不需

### 3.2 M6：前端 scaffolding

**範圍**：依規格 §4 建立 Next.js 14 + Tailwind + Apple Glassmorphism 三頁面骨架。

**關鍵元件**：

1. **API client 自動生成**：用 `openapi-typescript` 從 backend `/openapi.json` 生成 `.ts` 型別 → wrap 為 `lib/api/client.ts` 含 retry / timeout / Bearer token
2. **Auth provider**：React Context 管 token + 自動附加 `Authorization` header；登出時 clear localStorage
3. **三個核心頁面**：
   - `/`：上傳音檔 → 顯示辨識結果（呼叫 `POST /api/v1/asr/transcribe`）
   - `/history`：歷史辨識紀錄列表 + 詳情（呼叫 `GET /api/v1/asr/transcriptions`，**M5 補齊端點**）
   - `/keys`：API 金鑰管理（admin scope）
4. **UI 設計系統**：`components/ui/` 含 Button / Card / Input / Modal，遵守規格 §4.2 Apple 圓滑風格

**DoD**：
- `npm run dev` 啟動 OK
- `npm run build` 產出靜態檔
- 3 頁面 SSR + CSR 都正常
- Jest + React Testing Library 至少 15 個元件測試 PASS
- `npm run typecheck` 通過
- `npm run lint` 通過

**依賴**：
- M5 完成（前端需呼叫 hotword 端點 → 但 hotword UI 是 M9 範圍）
- 前端不阻擋 M7+ 後端進度（可並行）

**注意**：規格書 §4.5 列出完整目錄結構；本 milestone 只實作骨架與 3 頁面，complete UI（含 hotword / dataset / correction）分散到 M5+/M9+。

### 3.3 M7：ForcedAligner + 語者分離 + 後處理 + 糾錯管線

**範圍**：依規格 §3.3.2 / §3.3.3 / §3.3.5 / §16 實作四大 Vendor-only 模組。**M4 既有的 ASR 推理只回傳文字（無時間戳對齊）**，M7 開頭補上 Aligner 才能驅動後續模組。

**目錄補強**：`app/services/aligner/`（M7 新增，與既有 `services/audio/` / `services/asr/` 同層級）

**關鍵元件**：

1. **ForcedAligner**（規格 §3.3.2）：
   - 模型：`Qwen3-ForcedAligner-0.6B`（VRAM ~2 GB）
   - 切段限制：5 分鐘（規格約定）；長音檔分段處理
   - 啟動載入：M4 lifespan 既有結構擴充，與 `AsrEngineManager` 同層級
   - Service：`AlignerService.align(text, wav_path)` → `list[WordTimestamp]`
   - 失敗時跳過 → transcription 仍可完成但無時間戳（寫 `post_processing.aligner_failed`）
2. **語者分離**（規格 §3.3.3）：
   - 主：`pyannote.audio`（需 HF_TOKEN，VRAM ~2 GB）
   - Fallback：CAM++（純 CPU，速度較慢精度較低）
   - **Fine-tune 進行時強制降級 CAM++**（規格 §18.2，跨檔案決策）
   - 依賴 Aligner 的時間戳作為 speaker 切段邊界
   - Service：`DiarizationService.run(wav_path, alignments)` → `list[SpeakerSegment]`
3. **後處理**（規格 §3.3.4）：
   - 標點：簡單規則（句末、？！）
   - 數字正規化：「一二三」→「123」
   - 英文處理：保留原樣或全形對齊
   - 失敗時跳過，不阻擋辨識（規格約定）
4. **糾錯四層管線**（規格 §16）：
   - L1 **NEC**（命名實體糾錯，Generative-Annotation-NEC）：可選，VRAM ~1 GB
   - L2 **KenLM**（n-gram 語言模型）：純 CPU，二進位 ~500 MB
   - L3 **同音異字**（pinyin 對照）：純 CPU，輕量
   - L4 **LLM**（Qwen2.5-7B INT4）：VRAM ~4.5 GB，僅啟用時載入
   - 每層失敗跳過寫入 `post_processing` JSONB，**不可拋出例外中斷辨識**

**整合到 Transcriber**：M4 既有 `Transcriber.run(job)` 在 `mark_completed` 前插入「Aligner → diarization → 後處理 → 糾錯」流程。

**DoD**：
- ForcedAligner 載入 + 5 分鐘切段邏輯 PASS
- pyannote / CAM++ 切換 PASS
- 糾錯四層各別測試 + 全管線測試
- Fine-tune 模擬啟動時 pyannote 強制降級驗證
- `post_processing` JSONB 結構符合規格 §3.3.5
- `transcriptions.timestamps` 欄位實際寫入

**依賴**：
- M4 既有 Transcriber（編輯，非新建）+ AsrEngineManager 結構（複用，加 AlignerService 並列管理）
- M8 Fine-tune 隔離邏輯（透過 settings flag 或 file lock）

**VRAM 預算**（規格 §18.1）：基礎 4.1 GB（ASR 4 + VAD 0.1）+ Aligner 2 GB + pyannote 2 GB + NEC 1 GB + LLM 4.5 GB = 最大 13.6 GB。**Fine-tune 啟動時觸發降級**（不載 Aligner -2 GB、pyannote → CAM++ -2 GB、不載 NEC -1 GB、不載 LLM -4.5 GB，剩 ~4.1 GB 推理 + 31 GB 訓練 = 35.1 GB，48 GB GPU 留 13 GB 緩衝）。

### 3.4 M8：Fine-tune 管線

**範圍**：依規格 §3.3.6 / §15 / §18.2 實作 Fine-tune 任務管理與訓練 runner。

**關鍵元件**：

1. **Fine-tune 任務狀態機**：
   - `pending` → `preparing`（資料增強）→ `training` → `evaluating` → `completed` / `failed`
   - `FINETUNE_MAX_CONCURRENT=1` 強制（規格約定）
2. **資料增強**（規格 §15.3）：可選，速度擾動 / 加噪 / SpecAugment；由 `DATA_AUGMENTATION_ENABLED` ENV 控制
3. **訓練 runner**：
   - `scripts/finetune_runner.py` 獨立子程序（`subprocess.Popen`，非 `multiprocessing`）
   - LoRA / QLoRA 配置，學習率 `1e-4 → 1e-5`（規格 §15.1）
   - 透過 file-based checkpoint 機制與主程式溝通（避免 fork 衝突 vLLM）
4. **推理隔離**（規格 §18.2，**跨檔案決策**）：
   - Fine-tune 開始 → 寫入 `/data/finetune.lock` file
   - Transcriber 在 `run()` 開始檢查 lock → 若存在則：
     - 設 vLLM `batch_size=1`
     - `torch.cuda.set_per_process_memory_fraction(0.65)`
     - DiarizationService 強制使用 CAM++
     - 剩餘 VRAM < 8 GB 時暫停 Fine-tune（pause-resume 機制）
5. **Checkpoint 管理**：`finetune_checkpoints` 表記錄每個 epoch 的 loss / WER；`POST /api/v1/finetune/tasks/:id/promote` 把 checkpoint 切換為 active 模型

**API 端點**（規格 §3.4）：
- `POST /api/v1/finetune/upload` 上傳訓練資料
- `POST /api/v1/finetune/tasks` 建立任務
- `GET /api/v1/finetune/tasks` 列表
- `GET /api/v1/finetune/tasks/:id` 詳情含 loss history
- `POST /api/v1/finetune/tasks/:id/promote` 切換 active model（M4 雙模型策略對接）

**DoD**：
- 完整 Fine-tune 流程 e2e（mock LoRA，~1 分鐘完成）
- `FINETUNE_MAX_CONCURRENT=1` 強制驗證
- 推理隔離（lock file + memory fraction + pyannote 降級）端到端測試
- Checkpoint promote 觸發 M4 模型熱切換流程

**依賴**：
- M4 既有 `AsrEngineManager`（編輯加入 `swap_active_model` 方法）
- M7 既有 DiarizationService（編輯加 Fine-tune 旗標檢查）

### 3.5 M9：YouTube 下載 + 校正工作台

**範圍**：依規格 §3.3.7 / §14 / §3.3.8 實作 YouTube 音檔下載與標註校正流程。

**關鍵元件**：

1. **yt-dlp 包裝**（規格 §3.3.7）：
   - SSRF 防護：URL 解析必須符合 `^https?://(www\.)?(youtube\.com|youtu\.be)/`（**僅這兩個白名單**）
   - 限制 protocol 為 `https`
   - 下載前 HEAD 檢查 Content-Length，拒絕 > 1 GB
   - 下載至臨時目錄後重命名為 UUID
2. **YouTube 任務狀態機**：
   - `pending` → `downloading` → `transcribing`（呼叫 M4 transcribe pipeline）→ `ready_for_correction`
3. **校正工作台**（規格 §3.3.8）：
   - `correction_sessions` 表：一個 session 對應一個 transcription
   - `correction_segments` 表：每個段落獨立可編輯，含 `version` 欄位（Optimistic Locking）
   - 多人協作衝突時拋 `CORRECTION_VERSION_MISMATCH`（規格附錄 A）
4. **校正完成 → 加入 Dataset**：
   - 校正後的 `original_text` / `corrected_text` 寫入 `correction_segments`
   - `POST /api/v1/correction/sessions/:id/export-to-dataset` 將段落加入指定 dataset

**前端 UI**（M6 既有骨架擴充）：
- `frontend/app/correction/[session_id]/page.tsx`：分段顯示音檔波形 + 文字 + 編輯框
- WebSocket 不必用（簡單 polling 或 SWR 即可）

**API 端點**（規格 §3.4）：
- `POST /api/v1/dataset/youtube/download` 觸發下載 + 切段
- `GET /api/v1/correction/sessions/:id` 取得 session
- `PUT /api/v1/correction/sessions/:id/segments/:segment_id` 更新段落（含 `expected_version`）
- `POST /api/v1/correction/sessions/:id/export-to-dataset`

**DoD**：
- yt-dlp SSRF 白名單驗證（非 youtube URL 拒絕）
- 完整 YouTube → 下載 → 切段 → 校正 → Dataset 流程
- Optimistic Locking 衝突拋 409 驗證
- 前端校正 UI 三個基本操作（編輯 / 儲存 / 匯出）

**依賴**：
- M4 transcribe pipeline（複用，無修改）
- M5 Dataset（複用）
- M6 前端骨架（擴充）

### 3.6 M10：WebSocket 質檢接口

**範圍**：依規格 §3.3.9 / §3.3.7 實作即時質檢 WebSocket 端點。

**關鍵元件**：

1. **WS 端點**：`/ws/quality`（單端口 8000 共用 HTTP，規格 §3.1 強制）
2. **認證**（規格 §12，強制規範 12）：
   - 透過 `Sec-WebSocket-Protocol: asr.v1, bearer.<base64url(token)>`
   - **禁止 query string 傳遞 token**（會被 access log / Referer 洩漏）
   - 解析 protocol → base64url decode → token → 呼叫 M2 既有 `get_current_tenant` 邏輯
3. **心跳協議**（規格 §3.3.7）：
   - 前端每 30 秒送 `{"action": "ping"}`
   - 後端立刻回 `{"action": "pong", "timestamp": ...}`
   - **後端超過 90 秒未收 ping 主動斷線**（避免 zombie connection）
4. **連線限制**（規格 §3.3.7）：
   - 單金鑰最大連線數 `WS_MAX_CONNECTIONS_PER_KEY=10`
   - 訊息上限 `WS_MAX_MESSAGE_SIZE_MB=50`
5. **連線管理**：
   - `services/ws_quality/manager.py` 維護 `api_key_id → list[WebSocket]` 對應
   - 連線開啟時檢查上限，超過拒絕
   - 連線關閉時清理

**質檢內容**（Phase 2 範圍簡化）：
- Phase 2 僅實作連線、認證、心跳、訊息上限四項基礎能力
- 「即時轉錄」（chunked audio → ASR 增量輸出）屬 Phase 3 範圍，本 milestone 預留 hook

**DoD**：
- WS subprotocol 認證 PASS / 401
- 心跳 90 秒斷線驗證
- 多金鑰連線上限驗證
- 訊息超過 50 MB 斷線驗證

**依賴**：
- M2 既有認證機制（複用，無修改）
- M11 既有 ASR 路由（不互動）

### 3.7 M11：可觀測性 + 安全控管

**範圍**：依規格 §18 / §19 / §22 / §25 啟用 Prometheus、tracing、限流、CSP、安全標頭、軟刪除 + erase。

**關鍵元件**：

1. **Prometheus middleware 啟用**：
   - 從 M2 T2.10 的 no-op 升級為實裝
   - 既有 `app/middleware/prometheus.py` 改為 `prometheus_active.py`（保留 no-op 為 dev fallback）
   - Metrics：`http_requests_total`、`http_request_duration_seconds`、`asr_inference_duration_seconds`、`vad_segments_per_audio`、`gpu_memory_used_mb`
   - 暴露 `GET /metrics` 端點（Prometheus exposition format）
2. **OpenTelemetry tracing**：
   - Span：HTTP request → router → service → repository → DB / vLLM
   - 透過 `OTEL_EXPORTER_OTLP_ENDPOINT` ENV 配置 collector
3. **Sliding Window 限流**（規格 §19.4）：
   - `app/middleware/rate_limit_active.py` 升級
   - 預設每 api_key_id 60 req/min（可由 `api_keys.rate_limit_override` 覆寫）
   - 拒絕時回傳 `X-RateLimit-Limit` / `X-RateLimit-Remaining` / `X-RateLimit-Reset` headers
4. **CSP + 安全標頭**：
   - `Content-Security-Policy`、`Strict-Transport-Security`、`X-Content-Type-Options`、`X-Frame-Options`、`Referrer-Policy`
   - 由新 middleware `security_headers.py` 統一注入
5. **OpenAPI 文檔處置**（規格 §21.6）：
   - production 環境強制 `OPENAPI_DOCS_REQUIRE_AUTH=true`
   - `/docs` 端點檢查 admin scope，未授權 401
6. **軟刪除 + erase**（規格 §3.3.10）：
   - `DELETE /api/v1/auth/keys/:id` 軟刪除（寫 `deleted_at`）
   - `DELETE /api/v1/auth/keys/:id/erase` 徹底刪除含關聯 transcriptions / audit_logs，寫入 audit event `auth.key_erased`
7. **audit_logs 全面覆蓋**：補完所有 admin 操作的 audit event

**DoD**：
- `/metrics` 端點輸出 Prometheus 格式
- 限流 headers 正確
- CSP 標頭正確注入
- 軟刪除 + erase 端點驗證
- production profile 啟動時 `OPENAPI_DOCS_REQUIRE_AUTH=true` 強制
- 累積測試 ≥ 200

**依賴**：
- M2 既有 middleware 結構（替換 no-op 而非新增）
- M4 既有 lifespan（補 Prometheus / OTEL 初始化）

---

## 四、橫切關注點細部設計

### 4.1 VRAM 預算動態調整（規格 §18.1）

48 GB GPU 在不同情境下的 VRAM 配置：

| 情境 | ASR | VAD | Aligner* | pyannote | NEC | LLM | torch 訓練 | 剩餘 |
|------|-----|-----|----------|----------|-----|-----|-----------|------|
| Phase 1 終點（M4） | 4 GB | 0.1 GB | — | — | — | — | — | 43.9 GB |
| + Aligner（M7 啟用） | 4 | 0.1 | 2 | — | — | — | — | 41.9 |
| + Diarization（M7） | 4 | 0.1 | 2 | 2 | — | — | — | 39.9 |
| + 全糾錯（M7） | 4 | 0.1 | 2 | 2 | 1 | 4.5 | — | 34.4 |
| Fine-tune 啟動（降級） | 4 | 0.1 | — | CAM++（0） | — | — | 31 | 12.9 |

\* Aligner 在 M4 未實作，M7 開頭補上。降級時 Aligner 隨之卸載。

**降級邏輯**：
- 進入 Fine-tune 模式時依以下順序釋放：(1) LLM 4.5 GB → (2) NEC 1 GB → (3) pyannote 2 GB（→ CAM++）→ (4) Aligner 2 GB
- VRAM 動態查詢透過 `torch.cuda.memory_allocated()`，每分鐘採樣

### 4.2 Profile 切換對 router 註冊的影響

`DEPLOYMENT_PROFILE` 環境變數控制 router 啟用：

| Router | Client | Vendor |
|--------|--------|--------|
| `health` / `asr` | ✅ | ✅ |
| `hotword` / `dataset`（M5） | ✅ | ✅ |
| `finetune`（M8） | ❌ | ✅ |
| `youtube` / `correction`（M9） | ❌ | ✅ |
| `ws`（M10） | ✅ | ✅ |
| `metrics`（M11） | ✅ | ✅ |
| `auth_admin`（M11） | ✅ | ✅ |

`main.py` lifespan 啟動時依 `settings.DEPLOYMENT_PROFILE` 條件式 `app.include_router()`：

```python
if settings.DEPLOYMENT_PROFILE == "vendor":
    app.include_router(finetune_router)
    app.include_router(youtube_router)
    app.include_router(correction_router)
```

OpenAPI `/openapi.json` 因此自動隱藏 Vendor-only 端點，前端 typed client 不會看到。

### 4.3 Fine-tune 與推理隔離（規格 §18.2）

**檔案 lock 機制**：

```python
# services/finetune/lock.py
FINETUNE_LOCK = Path("/data/finetune.lock")

def acquire_finetune_lock() -> None:
    if FINETUNE_LOCK.exists():
        raise FinetuneConcurrentError()
    FINETUNE_LOCK.write_text(str(os.getpid()))

def is_finetune_active() -> bool:
    return FINETUNE_LOCK.exists()

def release_finetune_lock() -> None:
    FINETUNE_LOCK.unlink(missing_ok=True)
```

**Transcriber 整合**：

```python
# services/asr/transcriber.py（編輯既有）
class Transcriber:
    async def run(self, job: AsrJob) -> TranscribeOutcome:
        if is_finetune_active():
            self._apply_finetune_degraded_mode()
        # 既有邏輯...
    
    def _apply_finetune_degraded_mode(self) -> None:
        # 不直接改 vLLM 引擎（vLLM 啟動後參數不可變）
        # 改為跳過 Aligner、跳過 pyannote、跳過 LLM 糾錯
        self.skip_aligner = True
        self.skip_diarization = True
        self.skip_llm_correction = True
```

**Transcriber 範圍變動**：M4 既有 `run()` 函式增加 4 行（檢查 lock + 降級），不違反「函式 < 20 行」原則（目前 ~30 行，需重構為小函式）。

### 4.4 WebSocket 與 workers=1 強制（規格 §3.1）

**為什麼必須 `workers=1`**：WS connection 綁定到特定 worker process。多 worker 會破壞 connection manager 的 `api_key_id → connections` mapping（連線在 worker A、廣播訊息來自 worker B）。

**水平擴展屬 Phase 3**：Redis pub/sub + 獨立 Worker instance。

**單端口 8000 共用**：HTTP route 與 WS route 同 ASGI app 註冊，FastAPI 自動依 protocol 分流。

### 4.5 Hotword 三層架構切換邏輯（規格 §13.2 + §13.4）

```python
# services/hotword/dispatcher.py
def select_hotword_strategy(group_id: int, db: Session) -> HotwordStrategy:
    word_count = db.execute(
        select(func.count(Hotword.id)).where(Hotword.group_id == group_id)
    ).scalar_one()
    
    if word_count < settings.HOTWORD_SHALLOW_FUSION_THRESHOLD:  # 預設 100
        return ShallowFusionStrategy(group_id)
    if word_count < settings.HOTWORD_CTC_WS_THRESHOLD:  # 預設 1000
        return CtcWsStrategy(group_id)
    raise HotwordTooLargeError(
        message=f"Hotword 群組 {group_id} 超過 1000 詞，請建立 Fine-tune 任務",
        details={"word_count": word_count, "suggested_endpoint": "/api/v1/finetune/tasks"}
    )
```

**閾值由 ENV 覆寫**：`HOTWORD_SHALLOW_FUSION_THRESHOLD` / `HOTWORD_CTC_WS_THRESHOLD`，預設值依規格 §13.4。

### 4.6 糾錯四層管線失敗跳過策略（規格 §16.3）

```python
# services/correction/pipeline.py
async def run_correction_pipeline(text: str, options: CorrectionOptions) -> CorrectionResult:
    stages = []
    if options.nec_enabled:
        try:
            text = await NecCorrector.correct(text)
            stages.append({"layer": "nec", "status": "ok"})
        except Exception as e:
            stages.append({"layer": "nec", "status": "failed", "error": str(e)})
    
    if options.kenlm_enabled:
        try:
            text = KenlmCorrector.correct(text)
            stages.append({"layer": "kenlm", "status": "ok"})
        except Exception as e:
            stages.append({"layer": "kenlm", "status": "failed", "error": str(e)})
    
    # 同音、LLM 同樣失敗跳過
    return CorrectionResult(text=text, stages=stages)
```

**每層失敗寫入 transcription.post_processing JSONB**，**不拋出例外中斷辨識**。

### 4.7 Prometheus 啟用切換（middleware 替換策略）

M2 T2.10 既有 no-op middleware：

```python
# app/middleware/prometheus.py（M2 既有）
async def prometheus_middleware(request, call_next):
    return await call_next(request)
```

M11 升級時：

```python
# app/middleware/prometheus_active.py（M11 新增）
from prometheus_client import Counter, Histogram

REQUEST_COUNT = Counter("http_requests_total", "...", ["method", "endpoint", "status"])
REQUEST_DURATION = Histogram("http_request_duration_seconds", "...", ["endpoint"])

async def prometheus_active_middleware(request, call_next):
    start = time.monotonic()
    response = await call_next(request)
    duration = time.monotonic() - start
    REQUEST_COUNT.labels(method=request.method, endpoint=request.url.path, status=response.status_code).inc()
    REQUEST_DURATION.labels(endpoint=request.url.path).observe(duration)
    return response
```

**main.py 切換**：依 `settings.PROMETHEUS_ENABLED` 決定載入 active 或 no-op 版本。**保留 no-op 為 fallback**（dev 環境或 Prometheus 套件未裝時不阻擋啟動）。

### 4.8 OpenAPI docs production 強制（規格 §21.6 + §25.3）

`startup_checks.py` 既有檢查（M2 T2.11）：

```python
if settings.ENV == "production" and not settings.OPENAPI_DOCS_REQUIRE_AUTH:
    sys.exit("Production 模式必須 OPENAPI_DOCS_REQUIRE_AUTH=true")
```

M11 補充：實際 `/docs` 端點檢查 admin scope：

```python
# main.py
app = FastAPI(
    docs_url=None,  # 禁用預設 /docs
    redoc_url=None,
)

@app.get("/docs", include_in_schema=False)
async def custom_docs(api_key: ApiKey = Depends(require_scope("admin"))):
    return get_swagger_ui_html(openapi_url="/openapi.json", title="API")

@app.get("/openapi.json", include_in_schema=False)
async def custom_openapi(api_key: ApiKey = Depends(require_scope("admin"))):
    return app.openapi()
```

### 4.9 Phase 2 新增錯誤碼（擴充規格附錄 A）

| 錯誤碼 | HTTP | 用途 | Milestone |
|--------|------|------|-----------|
| `HOTWORD_GROUP_NOT_FOUND` | 404 | 群組不存在 | M5 |
| `HOTWORD_TOO_LARGE` | 422 | 超過 1000 詞需 Fine-tune | M5 |
| `DATASET_NOT_FOUND` | 404 | Dataset 不存在 | M5 |
| `DATASET_SAMPLE_INVALID` | 400 | 樣本資料不符 | M5 |
| `ALIGNER_NOT_READY` | 503 | ForcedAligner 未載入 | M7 |
| `ALIGNER_AUDIO_TOO_LONG` | 413 | 超過 5 分鐘上限 | M7 |
| `ALIGNER_FAILED` | 500 | 對齊失敗（不阻擋辨識） | M7 |
| `DIARIZATION_FAILED` | 500 | pyannote 推理失敗 | M7 |
| `DIARIZATION_NOT_READY` | 503 | pyannote 未載入 | M7 |
| `CORRECTION_LLM_UNAVAILABLE` | 503 | LLM 糾錯模型未載入 | M7 |
| `FINETUNE_CONCURRENT` | 409 | Fine-tune 已有任務在跑 | M8 |
| `FINETUNE_TASK_NOT_FOUND` | 404 | 任務不存在 | M8 |
| `FINETUNE_CHECKPOINT_NOT_FOUND` | 404 | checkpoint 不存在 | M8 |
| `FINETUNE_PROMOTE_FAILED` | 500 | 模型 promote 失敗 | M8 |
| `YOUTUBE_URL_INVALID` | 400 | 非 youtube.com / youtu.be | M9 |
| `YOUTUBE_DOWNLOAD_FAILED` | 502 | yt-dlp 下載失敗 | M9 |
| `YOUTUBE_FILE_TOO_LARGE` | 413 | > 1 GB | M9 |
| `CORRECTION_SESSION_NOT_FOUND` | 404 | session 不存在 | M9 |
| `CORRECTION_VERSION_MISMATCH` | 409 | Optimistic Locking 衝突 | M9 |
| `WS_AUTH_FAILED` | — | WS 認證失敗（close code 1008） | M10 |
| `WS_MAX_CONNECTIONS` | — | 超過單金鑰連線上限 | M10 |
| `WS_MESSAGE_TOO_LARGE` | — | 訊息 > WS_MAX_MESSAGE_SIZE_MB | M10 |
| `RATE_LIMIT_EXCEEDED` | 429 | Sliding Window 限流觸發 | M11 |

合計 23 個（含 M7 補上的 3 個 Aligner 錯誤碼）。實作位於 M2 既有 `app/core/exceptions.py` 擴充。

---

## 五、資料庫 Schema 新增

每個 milestone 對應的 Alembic migration：

| Migration | Milestone | 主要表 |
|-----------|-----------|--------|
| `0002_hotword_dataset.py` | M5 | `hotword_groups` / `hotwords` / `datasets` |
| `0003_finetune.py` | M8 | `finetune_tasks` / `finetune_checkpoints` |
| `0004_youtube_correction.py` | M9 | `youtube_downloads` / `correction_sessions` / `correction_segments` |
| `0005_audit_phase2.py` | M11 | `audit_logs.event_type` 擴充（無 schema 變動，僅 enum 補） |

**Schema 細節**：依規格 §5.4 - §5.11，本 design 不重複列出欄位。

**重要約定**：
- 所有新表沿用 M2 既有 mixin（`TimestampMixin` / `UpdatedAtMixin` / `TenantMixin`）
- 凡涉及租戶資料的表必須含 `api_key_id` 並透過 `TenantScopedRepository[T]` 存取
- 跨租戶的表（如 `correction_sessions` 可能多人協作）以 `version` 欄位實作 Optimistic Locking

---

## 六、API 端點完整清單

依規格 §3.4 列出 Phase 2 新增端點（不重複 Phase 1 已實作的 `/health` / `/readiness` / `/transcribe`）：

### M5 Hotword（6 個）
- POST `/api/v1/hotword/groups`
- GET `/api/v1/hotword/groups`
- GET `/api/v1/hotword/groups/:id`
- PUT `/api/v1/hotword/groups/:id`
- DELETE `/api/v1/hotword/groups/:id`
- POST `/api/v1/hotword/groups/:id/words/bulk`

### M5 Dataset（4 個）
- POST `/api/v1/dataset`
- GET `/api/v1/dataset`
- POST `/api/v1/dataset/:id/samples`
- GET `/api/v1/dataset/:id/samples`

### M8 Finetune（5 個）
- POST `/api/v1/finetune/upload`
- POST `/api/v1/finetune/tasks`
- GET `/api/v1/finetune/tasks`
- GET `/api/v1/finetune/tasks/:id`
- POST `/api/v1/finetune/tasks/:id/promote`

### M9 YouTube + Correction（7 個）
- POST `/api/v1/dataset/youtube/download`
- GET `/api/v1/dataset/youtube/downloads`
- GET `/api/v1/dataset/youtube/downloads/:id`
- GET `/api/v1/correction/sessions/:id`
- GET `/api/v1/correction/sessions/:id/segments`
- PUT `/api/v1/correction/sessions/:id/segments/:segment_id`
- POST `/api/v1/correction/sessions/:id/export-to-dataset`

### M10 WebSocket（1 個）
- `/ws/quality`（subprotocol `asr.v1, bearer.<token>`）

### M11 Metrics + Auth Admin（3 個）
- GET `/metrics`（Prometheus exposition）
- DELETE `/api/v1/auth/keys/:id`（軟刪除）
- DELETE `/api/v1/auth/keys/:id/erase`（徹底刪除）

**Phase 2 合計：26 個新端點**

所有 REST 端點必須遵守 M2 既有約定：
- 路徑前綴 `/api/v1/`
- `response_model=ResponseEnvelope[T]`
- `Depends(require_scope("..."))` 強制認證
- `Idempotency-Key` 支援（建立資源型）
- 列表 API 大欄位排除（`timestamps` / `speakers` / `post_processing` 等）

---

## 七、測試策略 / CI 補強 / ENV 新增

### 7.1 測試層次

| 層次 | 工具 | M5 | M6 | M7 | M8 | M9 | M10 | M11 |
|------|------|----|----|----|----|----|-----|-----|
| Unit | pytest | ✅ | Jest | ✅ | ✅ | ✅ | ✅ | ✅ |
| Integration | pytest + testcontainers | ✅ | — | ✅ | ✅ | ✅ | ✅ | ✅ |
| E2E | Playwright | — | ✅ | — | — | ✅ | — | ✅ |
| 效能 | locust / k6 | — | — | — | — | — | ✅ | ✅ |

### 7.2 CI 補強（`.github/workflows/ci.yml` 擴充）

| Job | 新增於 | 內容 |
|-----|--------|------|
| `frontend-lint-test` | M6 | `npm run lint && npm run typecheck && npm run test` |
| `frontend-build` | M6 | `npm run build`（檢查靜態檔產出） |
| `e2e-playwright` | M9 | Playwright headless 跑 3 個關鍵流程 |
| `security-scan` | M11 | `trivy fs .` + `bandit -r backend/app` + `pip-audit` |
| `prometheus-assert` | M11 | docker compose up 後 curl `/metrics`，grep 必要 metric 名 |

### 7.3 ENV 新增

| 變數 | 預設 | Milestone | 用途 |
|------|------|-----------|------|
| `HF_TOKEN` | — | M7 | pyannote 載入需要 |
| `KENLM_MODEL_PATH` | — | M7 | KenLM 二進位路徑 |
| `OPENAI_API_KEY` | — | M7 | LLM 糾錯（若採 OpenAI；自架 Qwen2.5 不需） |
| `LLM_CORRECTION_BACKEND` | `local` | M7 | `local` / `openai` |
| `HOTWORD_SHALLOW_FUSION_THRESHOLD` | `100` | M5 | 三層分流閾值 1 |
| `HOTWORD_CTC_WS_THRESHOLD` | `1000` | M5 | 三層分流閾值 2 |
| `FINETUNE_GPU_FRACTION` | `0.65` | M8 | 訓練 GPU memory 比例 |
| `FINETUNE_LOCK_PATH` | `/data/finetune.lock` | M8 | Lock file 位置 |
| `DATA_AUGMENTATION_ENABLED` | `false` | M8 | 資料增強開關 |
| `CORRECTION_KENLM_ENABLED` | `false` | M7 | KenLM 糾錯開關 |
| `YOUTUBE_DOMAIN_WHITELIST` | `youtube.com,youtu.be` | M9 | SSRF 防護白名單 |
| `YOUTUBE_MAX_DOWNLOAD_SIZE_MB` | `1024` | M9 | 下載上限 |
| `WS_MAX_MESSAGE_SIZE_MB` | `50` | M10 | （規格既有，M10 啟用）|
| `WS_MAX_CONNECTIONS_PER_KEY` | `10` | M10 | （規格既有，M10 啟用）|
| `PROMETHEUS_ENABLED` | `false` | M11 | middleware 啟用切換 |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | — | M11 | tracing 收集器 |
| `RATE_LIMIT_DEFAULT_PER_MIN` | `60` | M11 | 預設限流 |
| `FRONTEND_BASE_URL` | `http://localhost:3000` | M6 | 前端 base URL |

---

## 八、Phase 2 Exit Criteria

完整 Phase 2 完成的判準：

1. 7 個 milestone 全部 PASS（每個有獨立 plan 的整合驗收）
2. 累積測試 ≥ 200（Phase 1 結束 106）
3. 整體覆蓋率 ≥ 80%（Phase 1 結束 90.56%，新模組需維持）
4. `docker compose up`（Vendor profile）完整啟動，所有 service healthy
5. 真實 GPU smoke 全流程通過：上傳音檔 → transcribe → diarization → 糾錯 → 入 DB → 校正工作台編輯 → export 到 dataset → fine-tune trigger
6. `/metrics` 端點輸出 Prometheus 格式且有實際數據
7. 前端 3 個基本頁面 + 校正 UI 在 Chrome / Firefox / Safari 渲染正常
8. WebSocket `/ws/quality` 心跳 + 連線上限驗證通過
9. CI 全部 8 個 job PASS（M2 既有 5 + Phase 2 新增 3）

---

## 九、Phase 3 接口預留 / 風險清單

### 9.1 Phase 3 預留

- **水平擴展**：Redis 佇列、獨立 Consumer Worker、Redis pub/sub 支援 WS 多 worker
- **模型 registry**：完整模型版本管理（目前 M4 雙模型策略為簡化版）
- **多模型同時切換**：ASR + Aligner + Hotword + Diarization 統一切換
- **即時轉錄 WebSocket**：M10 預留 hook，Phase 3 接 chunked audio streaming
- **客戶 UI 完整化**：M6 僅 3 頁面骨架，Phase 3 補完 Hotword UI / Dataset UI / Finetune 監控

### 9.2 已知風險

| 風險 | 影響 | 緩解 |
|------|------|------|
| pyannote 商業授權 | 商業部署需付費或自架 | M7 plan 預先評估替代方案（CAM++ 已是 fallback） |
| torch 跨版本相容 | torchaudio 2.11 已踩 PHASE1-SPEC-05 | M7 / M8 plan 寫死 torch 版本，重大升級走獨立 milestone |
| Qwen2.5-7B INT4 VRAM 突發 | LLM 糾錯啟動時可能瞬時超過 4.5 GB | 設 INT4 memory_threshold，超過拒絕載入 |
| Fine-tune 中斷模型 corruption | 訓練到一半 OOM 導致 checkpoint 破損 | 每 epoch 寫 checkpoint，從最後一個有效 epoch 恢復 |
| yt-dlp 突然失效 | youtube 反爬蟲變更 | 釘版本 + plan 中標註重新驗證流程 |
| 前端 CSP 阻擋 inline style | Tailwind / framer-motion 可能與 CSP 衝突 | M11 設定 CSP `style-src 'self' 'nonce-...'` 配合 build hash |

### 9.3 已知缺口（本 design 不處理）

- Fine-tune ML 訓練演算法調優（屬 ML research，非工程範疇）
- pyannote 模型本身的精度評估（V2 加入 WER / DER 自動化評估）
- 多語言（除中 / 英外）支援
- 行動裝置原生 APP

---

## 十、與 CLAUDE.md 強制規範的對齊檢查

Phase 2 plan 必須通過以下檢查：

| 強制規範 | Phase 2 範圍對應 | 對應 plan |
|----------|----------------|-----------|
| 1（/api/v1/ 前綴） | 所有新 REST 端點 | 全部 |
| 2（ResponseEnvelope） | 所有 REST 回應 | 全部 |
| 3（標準分頁） | 列表 API（hotword / dataset / finetune / correction） | M5 / M8 / M9 |
| 4（列表大欄位排除） | transcriptions / correction_segments 列表 | M5 / M9 |
| 5（Tenant Isolation） | 所有租戶資料 repository | M5 / M8 / M9 |
| 6（Bearer + Scope） | 所有新端點（含 WS）| 全部 |
| 7（Idempotency-Key） | 建立資源型（POST `/hotword/groups` / `/dataset` / `/finetune/tasks` / `/youtube/download`） | M5 / M8 / M9 |
| 8（MIME magic bytes） | Dataset 樣本上傳、Finetune 資料上傳 | M5 / M8 |
| 9（檔名重寫 UUID） | 所有檔案上傳 | M5 / M8 / M9 |
| 10（16k mono WAV） | Dataset 樣本前處理 | M5 |
| 11（大檔分片） | Finetune 資料上傳 | M8 |
| 12（WS subprotocol 認證） | `/ws/quality` | M10 |
| 13（WS 心跳 30/90s） | `/ws/quality` | M10 |
| 14（WS 訊息上限） | `/ws/quality` | M10 |
| 15（時區） | 所有新表 `TIMESTAMP WITH TIME ZONE` | M5 / M8 / M9 |
| 16（Optimistic Locking） | `correction_segments.version` | M9 |
| 17（軟刪除） | `api_keys.deleted_at` + erase 端點 | M11 |
| 18（語言） | 所有 plan、commit 訊息 | 全部 |
| 19（Fine-tune 並發 = 1） | `FINETUNE_MAX_CONCURRENT=1` | M8 |
| 20（JSON Lines 日誌） | 既有 structlog | 全部 |
| 21（THIRD_PARTY_LICENSE_ACK） | startup_checks 既有 | 全部 |

---

## 撰寫紀錄

- 2026-05-16：建立，對應 Phase 1 完成後規劃。

---

**下一步**：本 design 確認後，依序撰寫 M5 → M6 → M7 → M8 → M9 → M10 → M11 共 7 份 plan。
