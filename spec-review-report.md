# Qwen3-ASR 設計規格書 v1.1 — 技術審查報告

**審查日期：** 2026-05-11
**審查對象：** [2026-05-11-qwen3-asr-platform-design.md](file:///d:/Qwen_asr/docs/superpowers/specs/2026-05-11-qwen3-asr-platform-design.md)

---

## 審查總覽

| 面向 | 問題數 | 嚴重等級 |
|------|--------|----------|
| A. 格式與一致性 | 5 | 低 |
| B. 技術事實性 | 4 | 中～高 |
| C. 架構設計缺失 | 7 | 高 |
| D. 資料庫設計缺口 | 4 | 中 |
| E. 安全性遺漏 | 4 | 高 |
| F. 改善優化建議 | 8 | 建議 |

---

## A. 格式與一致性問題

### A-1. 章節編號重複

**位置：** [第 254 行](file:///d:/Qwen_asr/docs/superpowers/specs/2026-05-11-qwen3-asr-platform-design.md#L254)

質檢 WebSocket 接口章節標示為 `3.3.5`，與前方文字後處理模組（第 184 行）編號重複。此節實際應為 `3.3.7`。

**修正：** 將第 254 行改為 `#### 3.3.7 質檢 WebSocket 接口`。

### A-2. 語法錯字混用

| 行號 | 錯誤 | 修正 |
|------|------|------|
| [138](file:///d:/Qwen_asr/docs/superpowers/specs/2026-05-11-qwen3-asr-platform-design.md#L138) | `vad Regions`（空格 + 大小寫錯誤） | `vad_regions` |
| [303](file:///d:/Qwen_asr/docs/superpowers/specs/2026-05-11-qwen3-asr-platform-design.md#L303) | `当前狀態`（簡體「当」） | `目前狀態` |
| [351](file:///d:/Qwen_asr/docs/superpowers/specs/2026-05-11-qwen3-asr-platform-design.md#L351) | `時間軸 ✓`（亂碼，原文為 `時間軸 ✓`，但實際顯示中有方塊字） | 改用純文字 `時間軸 [v]` |
| [470](file:///d:/Qwen_asr/docs/superpowers/specs/2026-05-11-qwen3-asr-platform-design.md#L470) | `側邊导航`（簡體「导」） | `側邊導航` |
| [705](file:///d:/Qwen_asr/docs/superpowers/specs/2026-05-11-qwen3-asr-platform-design.md#L705) | `错误處理設計`（簡體「错」） | `錯誤處理設計` |

### A-3. 前端專案結構中 public 區塊混入配置檔

**位置：** [第 509-513 行](file:///d:/Qwen_asr/docs/superpowers/specs/2026-05-11-qwen3-asr-platform-design.md#L509-L513)

`next.config.ts`、`tsconfig.json`、`Dockerfile`、`package.json` 被列在 `public/` 目錄下，但這些檔案屬於專案根目錄，非 public 資產。

**修正：** 將這些檔案移至 `frontend/` 根層級。另需補上 `docker/Dockerfile` 的路徑對應（與後端結構一致）。

### A-4. Fine-tune 章節編號跳躍

**位置：** [第 197 行](file:///d:/Qwen_asr/docs/superpowers/specs/2026-05-11-qwen3-asr-platform-design.md#L197)

章節 `3.3.6` 直接跳至第 254 行的 `3.3.5`（重複），中間缺少 `3.3.7`。Fine-tune 的子節使用 A/B/C/D/E 分段，但缺少明確的結束標記，讀者容易與後續章節混淆。

### A-5. REST API 端點表格缺少 ASR 相關端點

**位置：** [第 296 行](file:///d:/Qwen_asr/docs/superpowers/specs/2026-05-11-qwen3-asr-platform-design.md#L296)

3.4 節僅列出 Fine-tune 端點，缺少以下核心 API：
- `POST /api/asr/transcribe`（離線辨識）
- `GET /api/asr/status/:id`（辨識狀態查詢）
- `GET /api/history`（歷史記錄查詢）
- `GET /api/models`（模型列表）
- 歷史記錄相關 CRUD 端點

**修正：** 補上 ASR、歷史記錄、模型管理三組 REST API 端點表格。

---

## B. 技術事實性問題

### B-1. Qwen3-ASR 單段音檔上限為 20 分鐘，非 5 分鐘

**位置：** [第 145 行](file:///d:/Qwen_asr/docs/superpowers/specs/2026-05-11-qwen3-asr-platform-design.md#L145)、[第 711 行](file:///d:/Qwen_asr/docs/superpowers/specs/2026-05-11-qwen3-asr-platform-design.md#L711)

規格書寫道「音檔超過 5 分鐘時自動切段」，但根據官方文件，Qwen3-ASR 支援單檔最長 20 分鐘推理。5 分鐘限制僅適用於 **Qwen3-ForcedAligner-0.6B**（時間戳對齊模型）。

**修正方案：**
- ASR 推理本身不需要 5 分鐘切段，可支援到 20 分鐘
- 切段邏輯應僅在 ForcedAligner 階段執行：先用 ASR 對完整音檔（不超過 20 分鐘）推理，再將音檔切段送 ForcedAligner 取得時間戳
- 超過 20 分鐘的音檔才需要在 ASR 階段切段
- 錯誤處理表格第 711 行也需同步修正

### B-2. pyannote.audio VRAM 估算偏低

**位置：** [第 175 行](file:///d:/Qwen_asr/docs/superpowers/specs/2026-05-11-qwen3-asr-platform-design.md#L175)

規格書估算 pyannote.audio 為 2-4 GB VRAM，但根據實測資料，pyannote 3.1+ 在處理長音檔時可能尖峰達 6-9 GB。特別是 `discrete_diarization` 步驟會造成 VRAM 突波。

**修正方案：**
- 修正估算為 4-8 GB（含安全餘量）
- 重新計算剩餘 VRAM：48 - 4 (ASR) - 2 (Aligner) - 8 (pyannote) = ~34 GB
- 增加 pyannote 處理長音檔時的分段策略說明

### B-3. ClearVoice 安裝套件名稱可能不正確

**位置：** [第 693 行](file:///d:/Qwen_asr/docs/superpowers/specs/2026-05-11-qwen3-asr-platform-design.md#L693)

規格書寫 `ClearerVoice-Studio`，但實際 pip 安裝方式需要從 GitHub clone 後用 `pip install -e .`，並非標準 PyPI 套件名。需確認正確安裝方式。

**修正：** Dockerfile 中應明確列出 git clone + pip install 步驟，而非簡單列套件名。

### B-4. Qwen3-ASR 原生支援串流推理

**位置：** [第 726 行](file:///d:/Qwen_asr/docs/superpowers/specs/2026-05-11-qwen3-asr-platform-design.md#L726)

規格書將「實時串流辨識」列為 V2 擴展功能，但 Qwen3-ASR 本身已原生支援 streaming + offline 統一推理。此功能並非需要額外開發的擴展，而是模型已具備但平台未實作的能力。建議在 V1 就納入基礎串流支援的架構預留。

---

## C. 架構設計缺失

### C-1. 缺少健康檢查與監控機制

規格書缺少以下內容：
1. **健康檢查端點**（`GET /health`、`GET /readiness`）：雖在錯誤處理表提及 503，但未定義端點
2. **GPU 狀態監控端點**：查詢目前 VRAM 使用量、模型載入狀態
3. **佇列狀態端點**：查詢目前待處理數量、預估等待時間
4. **Prometheus/metrics 端點**：供外部監控系統收集指標

**修正：** 增加「十二、監控與可觀測性」章節，定義以下端點：

```
GET /health          → 基礎存活檢查
GET /readiness       → 含 DB + GPU + 模型載入就緒檢查
GET /api/metrics     → Prometheus 格式指標
GET /api/gpu/status  → VRAM 使用量、溫度、模型載入狀態
GET /api/queue/status → 佇列深度、預估等待時間
```

### C-2. 缺少日誌策略

規格書未定義：
1. 日誌格式（結構化 JSON logs 或純文字）
2. 日誌等級控制（環境變數 `LOG_LEVEL`）
3. 日誌儲存與輪替策略（Docker 環境下的 log driver 配置）
4. 請求追蹤（request ID / correlation ID）

**修正：** 增加日誌相關環境變數與策略說明。建議使用 `structlog` 或 `loguru` 搭配 JSON 格式輸出。

### C-3. 模型載入策略不明確

規格書提及模型初始化在 `main.py`，但缺少以下細節：
1. **啟動時載入**還是**按需載入**？所有模型（ASR + Aligner + pyannote + VAD + ClearVoice + NEC）同時載入將消耗大量 VRAM
2. **模型切換機制**：Fine-tune 完成後載入 checkpoint，是否需要 unload 舊模型？如何處理載入期間的請求？
3. **模型預熱**：首次推理通常較慢，是否在啟動時執行 warmup？

**修正：** 建議採用分層載入策略：
- 必載：ASR + Aligner + VAD（共 ~6.6 GB）
- 按需載入：pyannote（啟用 diarization 時）、ClearVoice（啟用降噪時）、NEC（啟用實體糾錯時）
- 啟動時對必載模型執行一次 dummy inference 作為預熱

### C-4. 缺少 CORS 與反向代理配置

前端與後端分離部署，但未提及：
1. FastAPI 的 CORS middleware 配置
2. 是否需要 Nginx/Traefik 反向代理
3. 前端 `NEXT_PUBLIC_API_URL` 在容器間通訊時應為內網 URL，非 `localhost`

**修正：**
- 後端 `config.py` 需增加 `CORS_ORIGINS` 環境變數
- docker-compose 中 `NEXT_PUBLIC_API_URL` 應改為 `http://asr-backend:8000`（SSR 用）
- 考慮加入 Nginx 容器做反向代理 + 靜態資源快取

### C-5. WebSocket 與 HTTP 共用同一 FastAPI 進程的問題

**位置：** [第 256 行](file:///d:/Qwen_asr/docs/superpowers/specs/2026-05-11-qwen3-asr-platform-design.md#L256)

質檢 WS 端口為 8001，但 FastAPI + Uvicorn 通常在單一進程上監聽單一端口。規格書未說明如何實現雙端口監聽。

**修正方案（三選一）：**
1. 使用單一端口 8000，WS endpoint 改為 `ws://host:8000/ws/quality`（推薦，最簡單）
2. 啟動兩個 Uvicorn 進程，分別監聽 8000 和 8001
3. 使用 Nginx 反向代理將 8001 導向同一 FastAPI 的 WS 端點

### C-6. asyncio Queue 在多 Worker 下的局限性

**位置：** [第 72 行](file:///d:/Qwen_asr/docs/superpowers/specs/2026-05-11-qwen3-asr-platform-design.md#L72)

使用 asyncio Queue 管理處理佇列屬記憶體內佇列，有以下風險：
1. **進程重啟遺失**：容器重啟後佇列中所有待處理任務消失
2. **多 Worker 不共享**：若啟用 Uvicorn 多 worker，各 worker 有獨立佇列
3. **無持久化**：大量音檔湧入時無法保證不遺失

**修正：** 在環境變數新增佇列策略選項：
- V1 可維持 asyncio Queue（但限制 Uvicorn 為單 Worker + 記錄佇列狀態到 DB）
- V2 升級為 Redis Queue（已列在擴展建議中，但 V1 應有降級容錯設計）

### C-7. 缺少音檔清理策略

規格書定義了音檔儲存路徑 `/data/audio`，但未定義：
1. 音檔保留期限（永久保留？自動清理？）
2. 磁碟空間監控與告警閾值
3. Fine-tune 訓練資料的生命週期管理

**修正：** 增加環境變數 `AUDIO_RETENTION_DAYS`（預設 30）與定時清理任務。

---

## D. 資料庫設計缺口

### D-1. 缺少索引定義

所有資料表均未定義索引。以下為必要索引：

```sql
-- transcriptions
CREATE INDEX idx_transcriptions_status ON transcriptions(status);
CREATE INDEX idx_transcriptions_created_at ON transcriptions(created_at DESC);
CREATE INDEX idx_transcriptions_source ON transcriptions(source);

-- finetune_tasks
CREATE INDEX idx_finetune_tasks_status ON finetune_tasks(status);

-- audio_files
CREATE INDEX idx_audio_files_transcription_id ON audio_files(transcription_id);

-- correction_sessions
CREATE INDEX idx_correction_sessions_session_id ON correction_sessions(session_id);
CREATE INDEX idx_correction_sessions_status ON correction_sessions(status);
```

### D-2. transcriptions 表缺少處理時長欄位

無法追蹤每次辨識的實際處理耗時（`processing_duration_sec`），這對效能監控與最佳化至關重要。

**修正：** 增加 `processing_duration_sec FLOAT` 欄位。

### D-3. 缺少資料庫遷移策略

規格書未提及使用 Alembic 或其他遷移工具管理 schema 變更。

**修正：** 在後端專案結構中增加：
```
backend/
  alembic/
    versions/
    env.py
  alembic.ini
```

### D-4. correction_sessions 表的 corrected_segments 設計疑慮

將校正逐句資料存為 JSONB 會導致：
1. 單一 segment 的更新需讀取/寫入整個 JSONB 欄位
2. 無法對單一 segment 做資料庫層級的並發控制

**建議：** 考慮拆為獨立的 `correction_segments` 表：

```sql
CREATE TABLE correction_segments (
    id SERIAL PRIMARY KEY,
    session_id INTEGER FK REFERENCES correction_sessions(id),
    segment_index INTEGER,
    speaker VARCHAR(50),
    start_time FLOAT,
    end_time FLOAT,
    original_text TEXT,
    corrected_text TEXT,
    is_modified BOOLEAN DEFAULT false,
    updated_at TIMESTAMP
);
```

---

## E. 安全性遺漏

### E-1. 無認證/授權機制

規格書未定義任何 API 認證機制。即使是內網部署，仍建議：
1. API Key 認證（最低要求）
2. 或 JWT Token 認證
3. WebSocket 連線認證（handshake 階段驗證 token）

**修正：** 增加 `API_KEY` 環境變數，所有端點要求 `Authorization: Bearer <key>` header。

### E-2. 音檔上傳缺少安全控制

未定義：
1. 單檔大小上限（未設限可能被惡意上傳巨大檔案）
2. 檔案類型實際校驗（僅靠副檔名判斷不安全，需用 magic bytes 驗證）
3. 上傳頻率限制（Rate Limiting）

**修正：** 增加以下環境變數：
```
MAX_UPLOAD_SIZE_MB=500
RATE_LIMIT_PER_MINUTE=30
```

### E-3. 資料庫密碼管理

**位置：** [第 640 行](file:///d:/Qwen_asr/docs/superpowers/specs/2026-05-11-qwen3-asr-platform-design.md#L640)

`DB_PASSWORD` 透過環境變數傳遞，但未提及 `.env` 檔案與 Docker secrets 機制。

**修正：** 增加 `.env.example` 檔案說明，並建議正式環境使用 Docker secrets。

### E-4. WebSocket 缺少訊息大小限制

base64 編碼的音檔直接透過 WebSocket 傳輸，未定義訊息大小上限。

**修正：** 增加 `WS_MAX_MESSAGE_SIZE_MB` 環境變數（建議預設 50 MB）。

---

## F. 改善優化建議

### F-1. 增加批次辨識 API

目前僅定義單檔辨識 API（`POST /api/asr/transcribe`）。對於企業級使用場景，建議增加：

```
POST /api/asr/batch          → 上傳多檔，回傳 batch_id
GET  /api/asr/batch/:id      → 查詢批次進度
GET  /api/asr/batch/:id/results → 取得批次結果
```

### F-2. 增加 SSE（Server-Sent Events）做辨識進度推送

目前前端需輪詢 API 取得辨識進度。建議增加 SSE 端點：

```
GET /api/asr/stream/:task_id → SSE 串流辨識進度與部分結果
```

這比 WebSocket 更輕量，且適合單向推送場景。Fine-tune 訓練進度也可改用 SSE 替代輪詢。

### F-3. 增加模型管理 API

規格書在專案結構中列出 `api/endpoints/models.py`，但未定義端點。建議：

```
GET    /api/models              → 列出所有可用模型（含 fine-tuned）
GET    /api/models/:id          → 模型詳情（VRAM 佔用、載入狀態）
POST   /api/models/:id/load     → 載入指定模型
POST   /api/models/:id/unload   → 卸載模型釋放 VRAM
DELETE /api/models/:id          → 刪除 fine-tuned 模型
```

### F-4. 校正工作台增加「批次自動校正」功能

校正工作台目前為純人工逐句校正。建議增加 LLM 輔助校正：
1. 使用 Qwen3 文字模型對 ASR 輸出做自動校正建議
2. 使用者可一鍵接受/拒絕建議
3. 可大幅減少人工校正時間

### F-5. 增加 Webhook 回呼機制

對於長時間音檔辨識與 Fine-tune 訓練，建議支援完成後主動 Webhook 通知：

```
POST /api/asr/transcribe
  body: { ..., "webhook_url": "https://your-system/callback" }
```

任務完成後主動 POST 結果至指定 URL。

### F-6. 前端增加 PWA 離線支援

工業環境可能網路不穩定。建議將前端建構為 PWA，支援：
1. 離線存取已載入的辨識結果
2. 離線上傳佇列（待網路恢復後自動上傳）

### F-7. 增加音檔波形視覺化元件

規格書提到 TimelineViewer，但未詳述波形視覺化實作。建議使用 `wavesurfer.js` 整合：
1. 即時波形顯示
2. 區域選取播放
3. 語者分段色彩標記直接繪製在波形上
4. 支援 zoom in/out

### F-8. 考慮 GPU 資源排程機制

規格書提到同時進行 Fine-tune 與推理時自動降低 batch size，但缺少具體的資源排程策略。建議：

1. 定義 GPU VRAM 分配優先級：推理 > Fine-tune
2. Fine-tune 開始前檢查 VRAM 餘量，自動計算可用 batch size
3. 若推理請求湧入，Fine-tune 應自動暫停讓出 VRAM
4. 增加 `GPU_RESERVE_FOR_INFERENCE_GB` 環境變數（預設 10 GB），確保推理始終有足夠資源

---

## 修正行動清單

> [!IMPORTANT]
> 以下為建議的修正優先順序。

| 優先級 | 項目 | 分類 |
|--------|------|------|
| P0 | B-1 修正切段邏輯（5 分鐘 vs 20 分鐘） | 技術事實 |
| P0 | A-5 補齊 ASR/歷史/模型 REST API 端點表格 | 完整性 |
| P0 | E-1 增加 API 認證機制設計 | 安全性 |
| P0 | C-5 釐清 WS 雙端口 vs 單端口方案 | 架構 |
| P1 | B-2 修正 pyannote VRAM 估算 | 技術事實 |
| P1 | C-1 補充健康檢查與監控端點 | 架構 |
| P1 | C-3 定義模型載入策略 | 架構 |
| P1 | C-6 定義佇列容錯機制 | 架構 |
| P1 | D-1 定義資料庫索引 | 資料庫 |
| P1 | E-2 增加上傳安全控制 | 安全性 |
| P2 | A-1~A-4 修正格式/編號/錯字 | 格式 |
| P2 | C-2 定義日誌策略 | 架構 |
| P2 | C-4 增加 CORS 與反向代理配置 | 架構 |
| P2 | C-7 定義音檔清理策略 | 架構 |
| P2 | D-2~D-4 資料庫補強 | 資料庫 |
| P2 | E-3~E-4 安全性補強 | 安全性 |
| P3 | F-1~F-8 改善優化建議 | 增強 |

---

**文件結束**
