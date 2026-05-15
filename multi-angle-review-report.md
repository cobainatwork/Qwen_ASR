# Qwen3-ASR 設計規格書 v1.4 — 多角度審查報告

**審查日期：** 2026-05-15
**審查對象：** `docs/superpowers/specs/2026-05-11-qwen3-asr-platform-design.md`（v1.4，1127 行）
**審查方式：** 5 個專業角度並行審查（Oracle 子代理）
**前次審查：** `spec-review-report.md`（v1.1，411 行，已修正）

---

## 審查總覽

| 面向 | P0 | P1 | P2 | P3 | 小計 |
|------|----|----|----|----|------|
| 後端架構 | 3 | 7 | 6 | 2 | 18 |
| 資安 | 4 | 5 | 5 | 3 | 17 |
| ML 工程 | 3 | 6 | 5 | 1 | 15 |
| 前端開發 | 4 | 5 | 6 | 2 | 17 |
| Docker/DevOps | 4 | 8 | 8 | 0 | 20 |
| **總計** | **18** | **31** | **30** | **8** | **87** |

---

## 一、後端架構審查

### P0 — 必須修正

#### P0-BE-1. 模型切換端點缺少版本隔離機制

| 項目 | 內容 |
|------|------|
| 位置 | 第 333 行、第 1102 行 |
| 問題 | `POST /api/asr/switch-model` 切換模型時，進行中的推理任務使用舊模型還是新模型？若舊模型 unload，進行中的推理會因 GPU 記憶體被回收而崩潰。無版本隔離，無法支援 A/B 測試或回滾。 |
| 建議 | (1) 實作「雙模型過渡」機制：新模型載入後，等待所有進行中的推理任務完成才 unload 舊模型；(2) 進行中的任務綁定到載入時的模型版本；(3) 新增 `model_version` 欄位至 `transcriptions` 表。 |

#### P0-BE-2. 處理管線順序：降噪應在 VAD 之前

| 項目 | 內容 |
|------|------|
| 位置 | 第 630-631 行（6.1 節） |
| 問題 | 規格書的處理順序為「VAD → 降噪 → ASR」，但 3.3.3 節寫「淨化音檔送入 VAD → ASR」，兩者矛盾。VAD 在噪音環境下會將高音量噪音誤判為語音，先降噪再 VAD 才能確保 VAD 的 F1 97.57% 指標成立。 |
| 建議 | 將 6.1 節處理順序修正為：「重取樣 → 可選降噪 → VAD → ASR 推理 → 對齊 → 語者分離 → 後處理」。 |

#### P0-BE-3. YouTube 下載部分失敗無處理策略

| 項目 | 內容 |
|------|------|
| 位置 | 第 607-615 行、第 778 行 |
| 問題 | 「音檔下載成功但字幕下載失敗」時 `subtitles` 欄位為 null。後續流程依賴字幕作為初始參考，若為 null 使用者體驗從「有初始字幕可修正」退化為「完全空白校正」。 |
| 建議 | (1) `youtube_downloads` 表增加 `subtitles_status` 欄位（`downloaded` / `partial` / `not_available`）；(2) 字幕失敗時自動觸發 ASR 產出初始文字；(3) 前端在字幕不可用時顯示警示。 |

### P1 — 高優先級

| 編號 | 問題 | 建議 |
|------|------|------|
| P1-BE-1 | asyncio Queue 單 Worker 缺少記憶體保護閥（100 個音檔可能 186 GB） | 新增 `QUEUE_REJECT_BEHAVIOR` 環境變數；V1 限定 MAX_QUEUE_SIZE = 20 |
| P1-BE-2 | torchrun 多 GPU 與單 GPU 部署環境矛盾，無 GPU 資源隔離 | 新增 `FINETUNE_GPU_DEVICE`；訓練啟動時自動偵測 GPU 數量；明確 VRAM 隔離策略 |
| P1-BE-3 | Checkpoint 管理缺少版本編號與自動清理 | 新增 `finetune_checkpoints` 獨立表；訓練完成後自動刪除非最佳 checkpoint |
| P1-BE-4 | pyannote 與 ASR 同時運行 VRAM 尖峰衝突（Fine-tune 進行時極易 OOM） | pyannote 每 3 分鐘分段；Fine-tune 期間語者分離降級為 CAM++ |
| P1-BE-5 | 缺少批次辨識 API 端點 | 新增 `POST /api/asr/batch`、`GET /api/asr/batch/:id`、`GET /api/asr/batch/:id/results` |
| P1-BE-6 | `correction_sessions` 表 JSONB 設計有並發問題 | 拆分為獨立的 `correction_segments` 表，每段為獨立列 |
| P1-BE-7 | 缺少 `datasets` 獨立資料表 | 新增 `datasets` 表，`finetune_tasks` 透過 `dataset_id` FK 關聯 |

### P2 — 中優先級

| 編號 | 問題 | 建議 |
|------|------|------|
| P2-BE-1 | Hotword 啟用歷史未記錄 | 新增 `hotword_group_history` 表或 `activated_at` 欄位 |
| P2-BE-2 | 後處理管線缺少錯誤隔離（NEC 失敗導致整個辨識失敗） | 每個可選步驟包在 try-catch 中，失敗時跳過並記錄警告 |
| P2-BE-3 | 8kHz 上採樣的準確率限制未警告 | `transcriptions` 表增加 `resampling_warning` 欄位 |
| P2-BE-4 | V2 Redis 升級路徑缺少相容性設計 | V1 即定義 `QueueBackend` 抽象介面 |
| P2-BE-5 | Fine-tune 訓練中斷的 process 清理未定義 | 記錄子行程 PID；取消時傳送 SIGTERM → SIGKILL |
| P2-BE-6 | 缺少 API 使用統計表 | 新增 `api_usage_logs` 表 |

### P3 — 建議

| 編號 | 問題 | 建議 |
|------|------|------|
| P3-BE-1 | Fine-tune 進度使用輪詢，增加伺服器負載 | 新增 SSE 端點主動推送 |
| P3-BE-2 | 模型切換無預先驗證 | 新增 `POST /api/asr/switch-model/dry-run` 端點 |

---

## 二、資安審查

### P0 — 必須修正

#### SEC-01. API_KEY 無輪換機制，無多使用者支援

| 項目 | 內容 |
|------|------|
| 位置 | 第 1108-1111 行（19.1 節）、第 803 行 |
| 問題 | 單一 `API_KEY` 環境變數，無 Token 輪換、無金鑰版本管理、無撤銷機制。金鑰外洩需重新部署整個容器。 |
| 建議 | 建立 `api_keys` 資料表（`key_hash`、`name`、`created_at`、`expires_at`、`is_active`），Argon2id 雜湊儲存。提供金鑰 CRUD API。健康檢查端點豁免認證。 |

#### SEC-02. 音檔上傳無 MIME type 實際校驗

| 項目 | 內容 |
|------|------|
| 位置 | 第 1113-1118 行（19.2 節）、第 824 行 |
| 問題 | 僅定義 `SUPPORTED_AUDIO_FORMATS` 字串清單，若僅檢查副檔名，攻擊者可將惡意可執行檔重新命名為 `.wav` 上傳。 |
| 建議 | 使用 `python-magic` 進行 MIME type sniffing；白名單驗證 magic bytes 必須落在 `audio/*`；上傳後以 UUID 命名儲存。 |

#### SEC-03. yt-dlp SSRF 風險

| 項目 | 內容 |
|------|------|
| 位置 | 第 946-978 行（14 節）、第 373 行 |
| 問題 | 使用者提供的 URL 直接傳入 `yt-dlp`，未限制網域/協議。攻擊者可指定內部網域 URL 利用 yt-dlp 洩漏雲端金鑰。 |
| 建議 | 白名單網域（僅 `youtube.com`、`youtu.be`、`youtube-nocookie.com`）；強制 `https://`；設定 `restrictfilenames=True`；獨立容器或沙箱執行 yt-dlp。 |

#### SEC-04. 音檔與逐字稿無加密儲存（at rest）

| 項目 | 內容 |
|------|------|
| 位置 | 第 52-61 行（2.2 節）、第 717-720 行 |
| 問題 | 音檔明文儲存於 `/data/audio`，逐字稿明文儲存於 PostgreSQL。企業級應用要求資料靜態加密。 |
| 建議 | 短期：LUKS 加密 Docker volume；中期：音檔 AES-256-GCM 加密；資料庫啟用 PostgreSQL TLS。 |

### P1 — 高優先級

| 編號 | 問題 | 建議 |
|------|------|------|
| SEC-05 | Rate Limiting 缺乏實作細節（無限制維度、無回應行為） | 使用 `slowapi`；依 API_KEY + IP 限制；不同端點不同限制 |
| SEC-06 | WebSocket 連線池無上限，有 DoS 風險 | 增加 `WS_MAX_CONNECTIONS`（預設 50）、`WS_MAX_CONNECTIONS_PER_IP`（預設 5） |
| SEC-07 | CORS 配置生產環境未定義 | 生產環境設定完整網域；明確 allow_methods / allow_headers |
| SEC-08 | GPU 資源無隔離機制（Fine-tune 可佔滿 VRAM 導致推理 DoS） | 增加 `GPU_RESERVE_FOR_INFERENCE_GB`；使用 `CUDA_VISIBLE_DEVICES` 隔離 |
| SEC-09 | 資料庫連線字串含明文密碼 | 生產環境使用 Docker secrets；啟用 PostgreSQL TLS |

### P2 — 中優先級

| 編號 | 問題 | 建議 |
|------|------|------|
| SEC-10 | 音檔清理機制可靠性未驗證（FastAPI 內無 cron daemon） | 使用 APScheduler；磁碟使用率超過 85% 發送告警 |
| SEC-11 | 日誌可能洩露敏感資料 | 結構化 JSON 日誌；`error_message` 僅記錄摘要 |
| SEC-12 | 缺少輸入驗證的 XSS 防護 | 後端字元過濾；前端不使用 `dangerouslySetInnerHTML` |
| SEC-13 | 容器映像未定義安全掃描 | 非 root 使用者運行；CI/CD 加入 Trivy 掃描 |
| SEC-14 | PostgreSQL 端口直接暴露到主機 | 移除 `ports: "5432:5432"` 映射，僅保留 Docker 內網通訊 |

### P3 — 建議

| 編號 | 問題 | 建議 |
|------|------|------|
| SEC-15 | 缺少安全標頭配置 | 增加 X-Content-Type-Options、X-Frame-Options、HSTS |
| SEC-16 | 無審計日誌（Audit Log） | 記錄 API_KEY 建立/撤銷、Fine-tune 任務、模型切換 |
| SEC-17 | 依賴套件供應鏈安全 | 使用 `pip-compile` 鎖定依賴版本 |

---

## 三、ML 工程審查

### P0 — 必須修正

#### ML-01. Fine-tune 模型切換無 zero-downtime 方案

| 項目 | 內容 |
|------|------|
| 位置 | 18.2 節（第 1102 行） |
| 問題 | 「載入新 checkpoint 前 unload 舊模型；載入期間請求進入佇列排隊」。模型載入需要數秒到數十秒，期間所有推理事務被阻斷，質檢 WebSocket 連線超時。 |
| 建議 | 雙模型交替策略：48 GB GPU 有足夠空間同時容納兩個 1.7B 模型（~8 GB）。實作 `ModelRegistry`，維持 `active` 與 `standby` 兩個模型實例，原子性切換。 |

#### ML-02. pyannote + ASR 同時運行時 VRAM 尖峰 OOM 風險

| 項目 | 內容 |
|------|------|
| 位置 | 3.3.4 節（第 191-197 行） |
| 問題 | VRAM 預算假設各模型為靜態值，pyannote 尖峰 9 GB + ASR 4 GB + Aligner 2 GB = 15.1 GB。若 Fine-tune 同時運行（~34 GB），總需求 49.1 GB 超過 48 GB。 |
| 建議 | (1) Fine-tune 期間 pyannote 強制降級為 CAM++；(2) ASR 完成後 `torch.cuda.empty_cache()` 再啟動 pyannote；(3) 剩餘 VRAM < 10 GB 時自動拒絕 pyannote。 |

#### ML-03. LLM 糾錯模型（Qwen2.5-7B）的 VRAM 需求未納入計算

| 項目 | 內容 |
|------|------|
| 位置 | 3.3.5 節第 217 行、16.1 節、10 節第 838-839 行 |
| 問題 | VRAM 預算完全沒有計算 Qwen2.5-7B。FP16 載入需 ~14 GB，INT4 量化需 ~4-5 GB。若 FP16 與 Fine-tune 同時運行必然 OOM。 |
| 建議 | (1) VRAM 預算表增加 Qwen2.5-7B 項目，明確指定 INT4 量化（~4.5 GB）；(2) 增加 `CORRECTION_LLM_QUANTIZATION` 環境變數。 |

### P1 — 高優先級

| 編號 | 問題 | 建議 |
|------|------|------|
| ML-04 | VAD 失敗時跳過直接送 ASR 的靜音污染風險 | 改為「能量閾值法」作為備用方案（RMS -40 dB） |
| ML-05 | VAD 切點精準度問題（MR 3.62% 漏語音，FAR 2.69% 誤判靜音） | 增加邊界擴展（margin padding）100-300 ms；記錄 `vad_confidence` |
| ML-06 | Fine-tune 驗證集資料來源未定義（資料洩漏風險） | 明確說明驗證集產生方式；資料量不足時警告 WER 可靠性 |
| ML-07 | Shallow Fusion decoder bias 的實作可行性未確認 | 驗證 Qwen3-ASR 是否支援 logits bias；不支援則改為後處理詞彙替換 |
| ML-08 | torchrun 多 GPU 與單 GPU 部署環境矛盾 | 改為「torchrun（V1 單 GPU，V2 支援多 GPU）」；使用 `accelerate` 替代 torchrun |

### P2 — 中優先級

| 編號 | 問題 | 建議 |
|------|------|------|
| ML-09 | 早停 patience=3 對於 ASR Fine-tune 偏短 | 改為 5；允許使用者調整（1-10 範圍） |
| ML-10 | 噪音資料庫 Docker 建構時下載造成映像過大（+10 GB） | 改為外部掛載卷，首次啟動時檢查並下載 |
| ML-11 | CTC-WS 手動觸發缺乏使用者指引 | 詞數達 80 時顯示提示；提供 A/B 對比功能 |
| ML-12 | 糾錯管線累積延遲未量化 | 補充各層典型延遲範圍；WS 接口預設關閉 LLM 糾錯 |
| ML-13 | 模型載入失敗回退機制不夠具體 | 定義回退層級：1.7B → 0.6B → HTTP 503 |

### P3 — 建議

| 編號 | 問題 | 建議 |
|------|------|------|
| ML-14 | `FINETUNE_SAVE_LIMIT` 保留策略不明確 | 明確指定「最佳 checkpoint + 最近 N-1 個」 |

---

## 四、前端開發審查

### P0 — 必須修正

#### P0-FE-1. 狀態管理方案不足以支撐即時任務追蹤

| 項目 | 內容 |
|------|------|
| 位置 | 4.1 節（第 389 行）、6.3 節（第 667 行） |
| 問題 | React Context + useReducer 缺乏內建的串流訂閱能力。輪詢在 React 18 Concurrent 模式下容易造成 state tearing。 |
| 建議 | 引入 TanStack Query 處理伺服器狀態（輪詢、快取、重試），Context 僅保留純前端 UI 狀態。 |

#### P0-FE-2. 長時間任務狀態同步機制未定義

| 項目 | 內容 |
|------|------|
| 位置 | 6.3 節（第 667 行）、6.4 節 |
| 問題 | 僅寫「前端透過輪詢 GET 更新進度」，未定義輪詢間隔、失敗重試、頁面切換後狀態恢復。 |
| 建議 | 採用 SSE 替代輪詢。新增 `GET /api/events` SSE 端點，前端以 `EventSource` 訂閱。 |

#### P0-FE-3. AudioPlayer 組件功能規格完全缺失

| 項目 | 內容 |
|------|------|
| 位置 | 4.4 節（第 452 行）、校正工作台 UI（第 236-250 行） |
| 問題 | 未定義波形顯示、播放速度調整、進度條拖曳、鍵盤快捷鍵、音量控制等核心功能。 |
| 建議 | 補充功能規格表：波形視覺化（wavesurfer.js）、播放速度（0.5x-2x）、鍵盤快捷鍵、循環播放、與 TranscriptViewer 雙向同步。 |

#### P0-FE-4. 校正工作台的自動儲存機制未定義

| 項目 | 內容 |
|------|------|
| 位置 | 3.3.6 節（第 229-250 行） |
| 問題 | 編輯過程中意外關閉分頁會遺失資料，對於可能持續數小時的校正工作是嚴重體驗缺陷。 |
| 建議 | 防抖自動儲存（停止輸入 2 秒後自動寫入後端）；UI 顯示「已儲存 / 儲存中 / 未儲存」指示器。 |

### P1 — 高優先級

| 編號 | 問題 | 建議 |
|------|------|------|
| P1-FE-5 | TranscriptViewer 時間軸同步邏輯未描述 | 定義雙向同步；`requestAnimationFrame` 驅動，避免每幀 re-render |
| P1-FE-6 | TimelineViewer 波形渲染方案未指定 | 採用 wavesurfer.js（v7+），支援 Regions 外掛標記語者分段 |
| P1-FE-7 | 大檔案上傳缺少前端進度條與斷點續傳 | React Dropzone + XMLHttpRequest；多檔上傳獨立進度條 |
| P1-FE-8 | Fine-tune 頁面 Tab 式布局缺少路由設計 | 採用 Next.js 子路由（`/finetune/correction`、`/finetune/training` 等） |
| P1-FE-9 | 辨識歷史頁缺少分頁/虛擬滾動策略 | cursor-based 分頁 + TanStack Query `useInfiniteQuery` + `@tanstack/react-virtual` |

### P2 — 中優先級

| 編號 | 問題 | 建議 |
|------|------|------|
| P2-FE-10 | 深色主題無障礙對比度未驗證 | 定義 CSS 變數色彩系統；開發時驗證 WCAG 2.1 AA（4.5:1） |
| P2-FE-11 | 未定義響應式設計策略 | 定義斷點策略（≥1280px 雙欄、768-1279px 單欄、<768px 收合） |
| P2-FE-12 | 網路斷線時的狀態恢復機制缺失 | API retry 邏輯（指數退避）；校正修改寫入 IndexedDB 本地備份 |
| P2-FE-13 | API 錯誤訊息的前端展示策略未定義 | 錯誤分級：4xx → Toast；5xx → Toast + 重試按鈕；不展示 traceback |
| P2-FE-14 | 音檔上傳前的前端預處理缺失 | File API + AudioContext 預檢（MIME、大小、取樣率、時長） |
| P2-FE-15 | 缺少 API 金鑰管理前端流程 | 首次開啟顯示設定頁；Token 儲存 localStorage；401 時清除並跳轉 |
| P2-FE-16 | Hotword 管理 UI 缺少批次操作 | 批次匯入（CSV/文字清單）、批次刪除勾選、批次 API 端點 |

### P3 — 建議

| 編號 | 問題 | 建議 |
|------|------|------|
| P3-FE-17 | 缺少前端效能監控 | Web Vitals 追蹤（LCP、FID、CLS）；端到端延遲記錄 |
| P3-FE-18 | 缺少 i18n 國際化規劃 | V2 評估引入 `next-intl` |

---

## 五、Docker / DevOps 審查

### P0 — 必須修正

#### P0-DEVOPS-1. PostgreSQL 缺少 healthcheck，depends_on 條件不可靠

| 項目 | 內容 |
|------|------|
| 位置 | 7.1 節，第 692-702 行 |
| 問題 | `depends_on: - postgres` 僅等待容器啟動，不等候資料庫就緒。後端啟動時 PostgreSQL 尚未接受連線，FastAPI 啟動失敗。 |
| 建議 | `depends_on: postgres: condition: service_healthy`；postgres 增加 `pg_isready` healthcheck。 |

#### P0-DEVOPS-2. 後端 Dockerfile 無多階段建構，映像體積過大

| 項目 | 內容 |
|------|------|
| 位置 | 7.2 節，第 747-753 行 |
| 問題 | 單一階段最終映像預估 12-15 GB。FlashAttention 2 需要編譯，但 runtime 映像不含 build 工具鏈，`pip install flash-attn` 會失敗。 |
| 建議 | 三階段建構：build 階段（devel 映像 + 編譯 FlashAttention/kenlm）→ deps 階段（pip install）→ runtime 階段（複製產物）。 |

#### P0-DEVOPS-3. 模型權重打包策略未定義

| 項目 | 內容 |
|------|------|
| 位置 | 7.2 節、第 57-58 行 |
| 問題 | 模型是在 build 階段下載還是 runtime 首次啟動時下載？Qwen3-ASR-1.7B 約 3.4 GB，若 runtime 下載首次啟動時間不可控。 |
| 建議 | 開發環境：bind mount，首次啟動自動下載。生產環境：Dockerfile build 階段 `huggingface-cli download` 嵌入映像或 init container 預先下載。 |

#### P0-DEVOPS-4. NVIDIA Container Toolkit 配置未描述

| 項目 | 內容 |
|------|------|
| 位置 | 全文件未提及 |
| 問題 | `deploy.resources.reservations.devices` 需要 host 安裝 NVIDIA Container Toolkit。未提及安裝步驟、Docker daemon 配置、驗證方式。 |
| 建議 | 新增 7.4 節描述安裝與驗證步驟。明確標註 Windows 開發環境僅用於前端開發和資料庫，後端 GPU 服務需在 Linux 環境運行。 |

### P1 — 高優先級

| 編號 | 問題 | 建議 |
|------|------|------|
| P1-DEVOPS-1 | docker-compose.yml 缺少 network 配置 | 建立 frontend/backend 兩個 network，backend 設 `internal: true` |
| P1-DEVOPS-2 | 缺少 restart 策略 | 所有服務增加 `restart: unless-stopped` |
| P1-DEVOPS-3 | asr-backend 缺少 healthcheck | 增加 `/health` healthcheck，start_period 60s（模型載入時間） |
| P1-DEVOPS-4 | 日誌管理完全缺失 | json-file driver，max-size 10m，max-file 5；增加 `LOG_LEVEL` 環境變數 |
| P1-DEVOPS-5 | 卷掛載權限問題（root vs 非 root） | Dockerfile 建立 `appuser`；entrypoint 執行 `chown` |
| P1-DEVOPS-6 | Fine-tune 時 GPU 資源限制不足 | 增加 `GPU_RESERVE_FOR_INFERENCE_GB`；Fine-tune 自動計算可用 VRAM |
| P1-DEVOPS-7 | `NEXT_PUBLIC_API_URL` 在瀏覽器端不可用（Docker 內部 hostname） | 瀏覽器端用 `localhost:8000`；SSR 端用 `asr-backend:8000`；或加 Nginx 反向代理 |
| P1-DEVOPS-8 | PostgreSQL 映像應使用 alpine 變體 | 改為 `postgres:16-alpine`（150 MB vs 400 MB） |

### P2 — 中優先級

| 編號 | 問題 | 建議 |
|------|------|------|
| P2-DEVOPS-1 | 缺少 `.dockerignore` 配置 | 排除 `__pycache__`、`.git`、`.env`、`data/`、`*.wav` |
| P2-DEVOPS-2 | 前端 Dockerfile 多階段建構細節不足 | 使用 Next.js standalone output 模式 |
| P2-DEVOPS-3 | 開發環境與生產環境配置未分離 | 使用 `docker-compose.override.yml` 開發覆蓋 |
| P2-DEVOPS-4 | Prometheus / Grafana 監控無規劃 | 至少新增 `/api/metrics` Prometheus 端點 |
| P2-DEVOPS-5 | 敏感環境變數注入方式不精確 | 生產環境使用 Docker secrets |
| P2-DEVOPS-6 | 音檔卷缺少磁碟空間告警機制 | `/health` 端點加入磁碟使用率檢查，超過 85% 返回警告 |
| P2-DEVOPS-7 | 未定義容器時區設定 | 所有服務增加 `TZ: Asia/Taipei` |
| P2-DEVOPS-8 | entrypoint 腳本缺失 | 建立 `entrypoint.sh`：Alembic 遷移 → 模型下載 → 權限修正 → Uvicorn |

---

## 跨領域關鍵風險

| 風險 | 涉及角度 | 嚴重度 | 相關項目 |
|------|---------|--------|----------|
| **VRAM 計算不完整** | ML、後端、DevOps | 極高 | ML-02、ML-03、P1-BE-4、SEC-08、P1-DEVOPS-6 |
| **認證機制過簡** | 資安、前端 | 高 | SEC-01、P2-FE-15 |
| **Fine-tune 與推理資源衝突** | ML、後端、DevOps | 高 | ML-01、ML-02、P1-BE-2、SEC-08 |
| **資料無加密** | 資安 | 高 | SEC-04 |
| **yt-dlp SSRF** | 資安 | 高 | SEC-03 |
| **Docker 映像過大/建構失敗** | DevOps、ML | 高 | P0-DEVOPS-2、ML-10 |
| **前端組件缺乏行為規格** | 前端 | 高 | P0-FE-3、P0-FE-4、P1-FE-5~9 |

---

## 修正行動清單

> 依優先順序排列，P0 為實作前必須完成。

### P0 修正清單（18 項，實作前必須完成）

| # | 項目 | 分類 | 規格書章節 |  effort |
|---|------|------|-----------|--------|
| 1 | P0-BE-2 修正處理管線順序（降噪 → VAD） | 架構 | 6.1 節 | Quick |
| 2 | SEC-01 建立 API_KEY 輪換機制 + 多金鑰支援 | 資安 | 19.1 節 | Medium |
| 3 | SEC-02 音檔上傳 MIME type 實際校驗 | 資安 | 19.2 節 | Quick |
| 4 | SEC-03 yt-dlp SSRF 防護（網域白名單 + 協議限制） | 資安 | 14 節 | Quick |
| 5 | SEC-04 音檔與逐字稿加密策略定義 | 資安 | 2.2 節、19 節 | Medium |
| 6 | ML-01 雙模型交替策略（zero-downtime 切換） | ML | 18.2 節 | Medium |
| 7 | ML-02 VRAM 尖峰 OOM 防護（Fine-tune 期間 pyannote 降級） | ML | 3.3.4、18.2 節 | Quick |
| 8 | ML-03 Qwen2.5-7B VRAM 納入計算（INT4 量化） | ML | 16.1、18.2 節 | Quick |
| 9 | P0-BE-1 模型切換版本隔離機制 | 架構 | 3.4 節 | Medium |
| 10 | P0-BE-3 YouTube 下載部分失敗處理策略 | 架構 | 5.7、8 節 | Quick |
| 11 | P0-FE-1 引入 TanStack Query 處理伺服器狀態 | 前端 | 4.1 節 | Medium |
| 12 | P0-FE-2 長時間任務 SSE 狀態同步 | 前端 | 6.3、6.4 節 | Medium |
| 13 | P0-FE-3 AudioPlayer 功能規格補充 | 前端 | 4.4 節 | Short |
| 14 | P0-FE-4 校正工作台自動儲存機制 | 前端 | 3.3.6 節 | Medium |
| 15 | P0-DEVOPS-1 PostgreSQL healthcheck + depends_on 條件 | DevOps | 7.1 節 | Quick |
| 16 | P0-DEVOPS-2 後端 Dockerfile 三階段建構 | DevOps | 7.2 節 | Medium |
| 17 | P0-DEVOPS-3 模型權重打包策略明確化 | DevOps | 7.2 節 | Quick |
| 18 | P0-DEVOPS-4 NVIDIA Container Toolkit 配置說明 | DevOps | 新增 7.4 節 | Quick |

### P1 修正清單（31 項，實作初期應完成）

| # | 項目 | 分類 | effort |
|---|------|------|--------|
| 19 | P1-BE-1 asyncio Queue 記憶體保護閥 | 架構 | Quick |
| 20 | P1-BE-2 torchrun GPU 資源隔離 | 架構 | Medium |
| 21 | P1-BE-3 Checkpoint 版本編號 + 自動清理 | 架構 | Medium |
| 22 | P1-BE-4 pyannote 分段策略 + Fine-tune 期間降級 | 架構 | Quick |
| 23 | P1-BE-5 批次辨識 API 端點 | 架構 | Medium |
| 24 | P1-BE-6 `correction_segments` 獨立表 | 架構 | Medium |
| 25 | P1-BE-7 `datasets` 獨立資料表 | 架構 | Medium |
| 26 | SEC-05 Rate Limiting 實作細節 | 資安 | Quick |
| 27 | SEC-06 WebSocket 連線數上限 | 資安 | Quick |
| 28 | SEC-07 CORS 生產環境配置 | 資安 | Quick |
| 29 | SEC-08 GPU 資源隔離機制 | 資安 | Quick |
| 30 | SEC-09 資料庫密碼安全注入 | 資安 | Quick |
| 31 | ML-04 VAD 失敗備用方案（能量閾值法） | ML | Quick |
| 32 | ML-05 VAD 切點邊界擴展 | ML | Quick |
| 33 | ML-06 Fine-tune 驗證集資料來源定義 | ML | Quick |
| 34 | ML-07 Shallow Fusion decoder bias 可行性確認 | ML | Quick |
| 35 | ML-08 torchrun 改為 accelerate（V1 單 GPU） | ML | Quick |
| 36 | P1-FE-5 TranscriptViewer 雙向同步邏輯 | 前端 | Short |
| 37 | P1-FE-6 TimelineViewer wavesurfer.js 整合 | 前端 | Medium |
| 38 | P1-FE-7 大檔案上傳進度條 + React Dropzone | 前端 | Medium |
| 39 | P1-FE-8 Fine-tune Tab 子路由設計 | 前端 | Short |
| 40 | P1-FE-9 歷史頁 cursor 分頁 + 虛擬滾動 | 前端 | Medium |
| 41 | P1-DEVOPS-1 docker-compose network 隔離 | DevOps | Quick |
| 42 | P1-DEVOPS-2 restart 策略 | DevOps | Quick |
| 43 | P1-DEVOPS-3 asr-backend healthcheck | DevOps | Quick |
| 44 | P1-DEVOPS-4 日誌管理配置 | DevOps | Quick |
| 45 | P1-DEVOPS-5 卷掛載權限 + 非 root 使用者 | DevOps | Quick |
| 46 | P1-DEVOPS-6 Fine-tune GPU 資源限制 | DevOps | Quick |
| 47 | P1-DEVOPS-7 NEXT_PUBLIC_API_URL 瀏覽器端修正 | DevOps | Quick |
| 48 | P1-DEVOPS-8 PostgreSQL alpine 變體 | DevOps | Quick |

### P2 修正清單（30 項，V1 後期或 V2）

| # | 項目 | 分類 |
|---|------|------|
| 49 | P2-BE-1 Hotword 啟用歷史記錄 | 架構 |
| 50 | P2-BE-2 後處理管線錯誤隔離 | 架構 |
| 51 | P2-BE-3 8kHz 上採樣準確率警告 | 架構 |
| 52 | P2-BE-4 V2 Redis 抽象層設計 | 架構 |
| 53 | P2-BE-5 Fine-tune process 清理 | 架構 |
| 54 | P2-BE-6 API 使用統計表 | 架構 |
| 55 | SEC-10 音檔清理機制可靠性 | 資安 |
| 56 | SEC-11 日誌敏感資料過濾 | 資安 |
| 57 | SEC-12 XSS 防護 | 資安 |
| 58 | SEC-13 容器安全掃描 | 資安 |
| 59 | SEC-14 PostgreSQL 端口不暴露 | 資安 |
| 60 | ML-09 早停 patience 調整為 5 | ML |
| 61 | ML-10 噪音資料庫改為外部掛載 | ML |
| 62 | ML-11 CTC-WS 使用者指引 | ML |
| 63 | ML-12 糾錯管線累積延遲量化 | ML |
| 64 | ML-13 模型載入失敗回退層級 | ML |
| 65 | P2-FE-10 深色主題對比度驗證 | 前端 |
| 66 | P2-FE-11 響應式設計策略 | 前端 |
| 67 | P2-FE-12 網路斷線狀態恢復 | 前端 |
| 68 | P2-FE-13 API 錯誤展示策略 | 前端 |
| 69 | P2-FE-14 前端音檔預處理 | 前端 |
| 70 | P2-FE-15 API 金鑰管理前端流程 | 前端 |
| 71 | P2-FE-16 Hotword 批次操作 | 前端 |
| 72 | P2-DEVOPS-1 .dockerignore 配置 | DevOps |
| 73 | P2-DEVOPS-2 前端 standalone output | DevOps |
| 74 | P2-DEVOPS-3 開發/生產配置分離 | DevOps |
| 75 | P2-DEVOPS-4 Prometheus metrics 端點 | DevOps |
| 76 | P2-DEVOPS-5 Docker secrets | DevOps |
| 77 | P2-DEVOPS-6 磁碟空間告警 | DevOps |
| 78 | P2-DEVOPS-7 容器時區設定 | DevOps |
| 79 | P2-DEVOPS-8 entrypoint 腳本 | DevOps |

### P3 修正清單（8 項，建議性質）

| # | 項目 | 分類 |
|---|------|------|
| 80 | P3-BE-1 SSE 進度推送 | 架構 |
| 81 | P3-BE-2 模型切換乾跑模式 | 架構 |
| 82 | SEC-15 安全標頭配置 | 資安 |
| 83 | SEC-16 審計日誌 | 資安 |
| 84 | SEC-17 依賴套件供應鏈安全 | 資安 |
| 85 | ML-14 checkpoint 保留策略明確化 | ML |
| 86 | P3-FE-17 前端效能監控 | 前端 |
| 87 | P3-FE-18 i18n 國際化規劃 | 前端 |

---

## 實作建議順序

### 第一階段：P0 修正（規格書更新）

1. 修正 6.1 節處理管線順序（降噪 → VAD）
2. 補充 19 節資安設計（API_KEY 輪換、MIME 校驗、SSRF 防護、加密策略）
3. 修正 18.2 節 VRAM 預算（加入 Qwen2.5-7B INT4、雙模型交替、pyannote 降級）
4. 補充 14 節 yt-dlp 安全限制
5. 補充 4.1 節前端狀態管理方案（TanStack Query + SSE）
6. 補充 AudioPlayer 功能規格
7. 修正 7 節 Docker 配置（healthcheck、三階段建構、network、NVIDIA Toolkit）

### 第二階段：P1 修正（實作初期）

- 資料庫設計補強（`datasets`、`correction_segments`、`finetune_checkpoints` 表）
- API 端點補齊（批次辨識、SSE 事件推送）
- 前端組件規格完善（TranscriptViewer、TimelineViewer、上傳進度）
- Docker Compose 完整配置（network、restart、logging、權限）

### 第三階段：P2/P3（V1 後期 / V2）

- 監控、日誌、審計
- Redis 佇列升級
- 效能優化、國際化

---

**文件結束**
