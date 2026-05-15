# Qwen3-ASR 離線語音辨識平台 — 設計規格書

**建立日期：** 2026-05-11
**最後更新：** 2026-05-16
**狀態：** v1.9 規格凍結版（涵蓋所有 P0/P1 修正、追加審查補強）
**版本：** v1.9
**技術棧：** Python FastAPI + Next.js 14 + PostgreSQL 16 (zhparser) + Docker Compose
**部署環境：** Linux + NVIDIA GPU 48 GB VRAM
**開發環境：** Windows + Docker

---

## 版本歷程 (Changelog)

### v1.9（2026-05-16）— 規格凍結，全數修正

**內部一致性修正：**
- 統一 `BACKEND_TYPE=vllm`（修正 docker-compose 中 `transformers` 殘留）
- 修正環境變數 `DISCLEANUP_SCHEDULE` → `DISK_CLEANUP_SCHEDULE` 拼字
- `youtube_downloads`、`hotwords` 表補 `api_key_id` 欄位（多租戶隔離防呆）
- 修正 15.1 Fine-tune 訓練參數表學習率異常（改為單調遞增 1e-5 → 5e-5）
- 所有 `TIMESTAMP` 欄位升級為 `TIMESTAMP WITH TIME ZONE`

**認證與多租戶強化：**
- 新增 19.1.1「API Scope 權限體系」（admin / asr:read / asr:write 等 10 種 scope）
- 3.3.7 補 WebSocket 認證機制（Sec-WebSocket-Protocol subprotocol 方案）
- `api_keys` 表補 `description`、`scopes`、`created_by_key_id`、`rate_limit_override`、`deleted_at` 欄位
- 新增軟刪除策略與徹底刪除（erase）流程

**可觀測性（全新章節）：**
- 新增 22 節「可觀測性」：JSON Lines 結構化日誌、敏感資料過濾、Prometheus 指標清單（16 項）、OpenTelemetry distributed tracing、日誌保留策略

**運維與合規（全新章節）：**
- 新增 23 節「SLO/SLA」：可用率、推理延遲、佇列等待時間目標
- 新增 24 節「災難復原」：PostgreSQL/Checkpoint/音檔備份策略，RPO/RTO 定義
- 新增 25 節「個資合規與資料保留」：當事人權利 API、`audit_logs` 表、資料分類
- 新增 26 節「第三方授權清單」：模型、套件、資料集授權審計

**API 設計強化：**
- 全部端點加 `/api/v1/` 前綴
- 新增 3.6.1「API 版本控管策略」（Semver、棄用週期、Sunset header）
- 新增 3.6.2「冪等性（Idempotency-Key）」規範
- 新增 cursor-based 分頁與「列表 API 大欄位排除規則」
- 新增批次辨識 API（`/api/v1/asr/batch`）
- 新增分片上傳 API（`/api/v1/asr/upload/*`）與 `chunked_uploads` 暫存表

**資料表強化：**
- 新增 5.10 `datasets` 表（一級實體，支援版本與品質追溯）
- 新增 5.11 `finetune_checkpoints` 表（取代 `finetune_tasks.best_checkpoint` 字串欄位）
- 新增 `audit_logs` 表（25.5 節）
- `correction_segments` 補 `version` 欄位（optimistic locking）
- `finetune_tasks` 移除 `dataset_path`、`dataset_quality_score`，改用 `dataset_id` FK

**模型與推理：**
- 佇列分 `realtime` / `batch` 雙通道，含優先級調度規則
- 新增 18.1.1「GPU 故障情境行為」
- 新增 18.3「模型載入失敗 Fallback 決策表」
- 7.2 補模型權重 SHA256 完整性驗證

**全文檢索：**
- 11 節擴充為 `11.1 索引清單 + 11.2 zhparser 中文全文檢索`
- postgres 映像改為自訂建構（含 zhparser 編譯）

**資安強化：**
- 19.2.1 補 Rate Limiting 演算法（Sliding Window Counter）
- 19.3.1 補安全標頭與 CSP 規範
- 19.3.2 補 OpenAPI 文檔處置（生產環境限 admin scope）

**CI/CD：**
- 20.1 擴充至 13 個檢查階段（含 migration、API contract、E2E、授權審計、secret 掃描）

**錯誤處理：**
- 8 節錯誤處理表補錯誤碼欄位
- 新增附錄 A「錯誤碼字典」（涵蓋 60+ 錯誤碼）

### v1.8（2026-05-15）— 前端架構修正
新增：Zustand 本地狀態管理、OpenAPI 型別同步策略、Vitest/Playwright 測試策略、動態路由、hooks/ 目錄、UI 元件擴充至 15 個、效能策略、無捲軸版面規劃。

### v1.4 ~ v1.7（2026-05-12 ~ 2026-05-14）
多角度審查 18 項 P0 與部分 P1 修正（vLLM 強制採用、雙模型交替、SSE 推送、API 認證、SSRF 防護等）。

### v1.1 ~ v1.3
初審報告修正（切段邏輯、API 端點補齊、單端口方案、認證機制設計）。

---

## 一、專案目標

基於 Qwen3-ASR 打造本地化離線語音辨識平台，提供企業級的音檔辨識、逐字稿產出、語者分離、文字後處理與模型微調能力。

### 核心功能
- 離線上傳語音辨識
- 逐字稿 + 時間軸輸出
- 語者分離（Speaker Diarization）
- 文字後處理（簡繁轉換、特殊字元移除、全形轉半形、數字轉換、文字正規化）
- Fine-tune 微調功能（含校正工作台）
- WebSocket + HTTP 雙接口供外部質檢系統對接
- 辨識歷史記錄管理
- 多格式文件自動轉換 JSONL（xlsx、srt/vtt、txt 等）
- Hotword / 自訂詞彙功能（三層架構）
- YouTube 音檔下載與 Dataset 建立
- 音檔取樣率自适应處理（8kHz-48kHz）
- 資料集品質評估

---

## 二、系統架構

### 2.1 容器架構（Docker Compose）

```
┌─────────────────┐    HTTP/WS     ┌─────────────────┐
│  asr-frontend   │ ◄────────────► │  asr-backend    │
│  Next.js 14     │                │  Python FastAPI │
│  :3000          │                │  :8000          │
└─────────────────┘                └────────┬────────┘
                                           │ GPU
┌─────────────────┐                        │
│  postgres       │◄────── DB Connection   │
│  :5432          │                        ▼
└─────────────────┘              ┌─────────────────┐
                                  │  NVIDIA GPU     │
                                  │  48 GB VRAM     │
                                  └─────────────────┘
```

### 2.2 儲存卷配置

| 掛載路徑 | 用途 |
|----------|------|
| `/data/audio` | 音檔存放（原始 + 預處理） |
| `/data/models` | Qwen3-ASR 模型權重 |
| `/data/checkpoints` | Fine-tune checkpoint 儲存 |
| `/data/postgres` | PostgreSQL 資料持久化 |
| `/data/noise-dataset` | 資料增強噪音資料庫 |

### 2.3 部署配置檔 (Deployment Profiles)

系統支援兩種實體的部署模式，藉由環境變數控制啟用模組：
- **Client Profile（甲方部署）**：專注於線上高併發生產環境。**僅啟用** ASR 推理、WebSocket、歷史紀錄與 Hotword 模組。硬性關閉 Fine-tune 與校正工作台，確保 VRAM 全數用於推理吞吐。
- **Vendor Profile（乙方代管）**：專注於訓練、資料處理與模型驗證。**全模組啟用**，包含：ASR 推理、WebSocket、歷史紀錄、Hotword 模組，以及校正工作台、資料集轉換與 Fine-tune 訓練模組。藉由調低 `VLLM_GPU_MEMORY_UTILIZATION`，確保底層 ASR 推理引擎與 `torchrun` 訓練任務能安全共存於同一張 GPU。

---

## 三、後端服務設計

### 3.1 技術棧
- **語言：** Python 3.12
- **框架：** FastAPI + Uvicorn（workers=1，因 WebSocket + HTTP 共用端口 8000；多 worker 模式下 WebSocket 連線會綁定到特定 worker，導致連線管理複雜）
- **ASR 模型：** Qwen3-ASR-1.7B（主力）+ Qwen3-ASR-0.6B（高併發備用）
- **對齊模型：** Qwen3-ForcedAligner-0.6B
- **VAD 語音活動檢測：** FireRedVAD（0.6M 參數，F1 97.57%，ASR 前端必備）
- **語音增強：** ClearVoice（整合降噪 + 音源分離，ASR 前端可選）
- **語者分離：** pyannote.audio（主方案）+ CAM++（備用，可純 CPU 運行）
- **文字處理：** opencc（簡繁）、自寫正規化模組
- **命名實體糾錯：** Generative-Annotation-NEC（SS+GL 架構，可選後處理步驟）
- **推理加速：** 強制採用 vLLM (AsyncLLMEngine) 作為底層 ASR 核心
- **佇列管理：** asyncio Queue（記憶體佇列，管理大量音檔處理順序）
- **資料庫：** PostgreSQL 16 + SQLAlchemy ORM
- **音檔下載：** yt-dlp（YouTube 音檔下載）
- **音檔重取樣：** torchaudio / soxr（取樣率自适应）

### 3.2 專案結構

```
backend/
  app/
    main.py                     # FastAPI 入口 + 模型初始化
    config.py                   # 設定管理（環境變數）
    models/
      asr.py                    # ASR 推理引擎封裝
      vad.py                    # VAD 語音活動檢測（FireRedVAD）
      enhancement.py            # 語音增強降噪（ClearVoice，可選）
      diarization.py            # 語者分離引擎封裝（pyannote / CAM++）
      text_normalize.py         # 文字後處理模組
      nec.py                    # 命名實體糾錯（Generative-Annotation-NEC，可選）
      hotword.py                # Hotword 管理與解碼器 bias
      finetune.py               # Fine-tune 訓練管理器
      augmentation.py           # 資料增強管線
    api/
      dependencies.py           # 共用依賴注入
      endpoints/
        asr.py                  # 離線辨識 API
        finetune.py             # Fine-tune API
        history.py              # 歷史記錄 API
        models.py               # 模型管理 API
        hotword.py              # Hotword 管理 API
        dataset.py              # Dataset 管理 API（YouTube 下載）
      websocket/
        quality.py              # 質檢 WS 接口
    services/
      asr_service.py            # ASR 業務邏輯 + 處理佇列管理
      audio_service.py          # 音檔預處理、儲存管理、取樣率自适应
      vad_service.py            # VAD 語音活動檢測服務
      enhancement_service.py    # 語音增强降噪服務（可選）
      finetune_service.py       # 訓練任務調度 + 資料驗證
      correction_service.py     # 校正工作台服務
      conversion_service.py     # 多格式轉換 JSONL 服務
      normalization_service.py  # 文字後處理管道
      nec_service.py            # 命名實體糾錯服務（可選）
      hotword_service.py        # Hotword 服務
      youtube_service.py        # YouTube 下載服務
      augmentation_service.py   # 資料增強服務
      db_service.py             # 資料庫操作
    db/
      base.py                   # SQLAlchemy Base
      models.py                 # ORM 模型定義
    storage/
      audio_manager.py          # 音檔檔案管理
      checkpoint_manager.py     # Checkpoint 管理
    docker/
      Dockerfile
      requirements.txt
    alembic/
      versions/                   # 資料庫遷移腳本
      env.py
    alembic.ini
```

### 3.3 功能模組詳細設計

#### 3.3.1 ASR 推理引擎

**功能：** 載入 Qwen3-ASR 模型並執行離線推理
**後端選擇：** 強制採用 vLLM (AsyncLLMEngine)
**輸入：** 音檔路徑 / URL / base64 / (np.ndarray, sample_rate)
**輸出：** `TranscriptionResult` 物件

```python
@dataclass
class TranscriptionResult:
    language: str
    text: str
    time_stamps: List[TimeStamp]
    speakers: List[SpeakerSegment]      # 僅啟用 diarization 時
    normalized_text: str                # 後處理後的文字
    vad_regions: List[VadRegion]         # VAD 偵測到的語音區段
    confidence: float                   # 辨識置信度
```

**推論與排程策略 (vLLM 架構)：**
- 全面廢除 `ProcessPoolExecutor` 多行程機制。改為直接在 FastAPI 初始化時啟動 vLLM 的 `AsyncLLMEngine`。
- **無阻塞並發**：利用 vLLM 原生的非同步 (Asynchronous) 特性，FastAPI 路由可直接執行 `await engine.generate()`，不阻擋事件迴圈，完美解決 GIL 阻塞問題。
- **連續批次處理 (Continuous Batching)**：vLLM 會在底層自動進行動態 Batching，Phase 1 的單卡高併發吞吐量獲得指數級提升。
- 透過佇列管理待處理音檔，避免 GPU OOM
- 依 GPU 剩餘 VRAM 自動調整 batch size
- ASR 推理支援單檔最長 20 分鐘；超過 20 分鐘才切段
- ForcedAligner 限制單段 5 分鐘：ASR 完成後，切段送 ForcedAligner 取得時間軸
- OOM 時自動降 batch size 後重試
- 佇列支援取消、優先級排序

**佇列抽象層設計：**
- V1 即定義 QueueBackend 抽象介面，避免 V2 Redis 升級時重構
- 介面定義：enqueue()、dequeue()、cancel()、status()、size()
- V1 預設實作：AsyncioQueueBackend（基於 asyncio.Queue + asyncio.PriorityQueue）
- V2 擴展實作：RedisQueueBackend（基於 Redis Streams + Consumer Group）
- 業務邏輯僅依賴抽象介面，不直接操作具體實作

**雙通道優先級設計：**

質檢 WebSocket 與離線 HTTP 上傳對延遲容忍度差異極大，**強制分為兩條獨立佇列通道**：

| 通道 | 用途 | 容量上限 | 推理 batch size 上限 | 優先級 |
|------|------|---------|---------|--------|
| `realtime` | 質檢 WS 任務、即時請求 | `QUEUE_REALTIME_MAX_SIZE`（預設 50） | 1（不批次以最小化延遲） | 高 |
| `batch` | 離線 HTTP 上傳、YouTube 轉錄、批次辨識 | `QUEUE_BATCH_MAX_SIZE`（預設 20） | `MAX_INFERENCE_BATCH`（預設 32） | 低 |

**排程規則：**
- vLLM AsyncLLMEngine 每次調度時，**優先消耗 realtime 佇列**
- realtime 佇列為空時才處理 batch 任務
- batch 任務處理中若有 realtime 任務入列，**待當前 batch step 完成後立即切換**（不取消進行中的 token 生成）
- 多個 realtime 任務間採 FIFO（無進一步優先級區分）

**佇列滿載拒絕策略：**
- `QUEUE_REJECT_BEHAVIOR`：`reject`（預設，回 HTTP 503 `QUEUE_FULL`） / `wait`（持有連線等待，最長 60 秒）
- realtime 滿載直接 reject（質檢需要明確失敗訊號重試）
- batch 滿載依設定行為

程式碼結構參考：

```python
from abc import ABC, abstractmethod
from enum import Enum

class QueuePriority(str, Enum):
    REALTIME = "realtime"
    BATCH = "batch"

class QueueBackend(ABC):
    @abstractmethod
    def enqueue(self, job: AsrJob, priority: QueuePriority) -> str: ...
    @abstractmethod
    async def dequeue(self) -> AsrJob:
        """優先 realtime，次 batch；皆空時阻塞。"""
        ...
    @abstractmethod
    def cancel(self, job_id: str) -> bool: ...
    @abstractmethod
    def status(self, job_id: str) -> dict: ...
    @abstractmethod
    def size(self, priority: QueuePriority | None = None) -> int: ...
```

#### 3.3.2 VAD 語音活動檢測（FireRedVAD）

**定位：** ASR 管線必裝前置處理步驟，經 Speech-Processing-Paper 實戰經驗驗證
**模型：** FireRedVAD（0.6M 參數，~2.2 MB）
**效能：** F1 97.57%、FAR 2.69%、MR 3.62%（FLEURS-VAD-102 多語言集）
**流程：**
1. 輸入音檔（原始音檔或降噪後的淨化音檔）→ VAD 偵測語音區段
2. 過濾純靜音/噪音片段
3. 僅將語音區段送入 ASR，減少推理時間，提升準確率

#### 3.3.3 語音增強降噪（可選）

**定位：** 前置可選處理步驟，質檢音檔有背景噪音時建議啟用
**模型：** ClearVoice（整合降噪 + 音源分離）
**流程：**
1. 原始音檔 → ClearVoice 降噪
2. 輸出淨化音檔送入 VAD → ASR 管線

#### 3.3.4 語者分離模組

**主方案：** pyannote.audio（GPU 加速）
**備用方案：** CAM++（可純 CPU 運行，支援全離線）

**VRAM 預算分配（48 GB GPU）：**
- Qwen3-ASR-1.7B：~4 GB
- ForcedAligner-0.6B：~2 GB
- FireRedVAD：~0.1 GB（極輕量）
- pyannote.audio：~4-8 GB（尖峰可能達 9 GB）
- Qwen2.5-7B（INT4 量化）：~4.5 GB（LLM 糾錯，按需載入）
- 推理保留上限：~16 GB（含安全餘量）
- 剩餘可用於 Fine-tune：~32 GB

**OOM 防護策略：**
- Fine-tune 運行期間，pyannote 強制降級為 CAM++（純 CPU）
- ASR 完成後執行 `torch.cuda.empty_cache()` 再啟動 pyannote
- 剩餘 VRAM < 10 GB 時自動拒絕 pyannote，回退至 CAM++
- pyannote 處理長音檔時每 3 分鐘分段，避免 VRAM 突波

**流程：**
1. ASR 先輸出全段逐字稿 + 時間戳
2. 對原始音檔執行 pyannote 語者分段
3. 將語者標籤與 ASR 時間戳資料對齊
4. 輸出格式：`[{speaker: "SPEAKER_00", start: 1.2, end: 5.8, text: "..."}, ...]`

#### 3.3.5 文字後處理模組

**處理管道（依序）：**
1. **命名實體糾錯（NEC，可選）：** Generative-Annotation-NEC SS+GL 架構，修正專業術語、中英夾雜（例：「米德仲尼」→ 「Midjourney」）
2. **標點預測（可選）：** 對 ASR 原始輸出補上標點符號
3. **KenLM 語言模型重新評分（可選）：** 基於領域語料的 n-gram 語言模型
4. **簡繁轉換：** opencc 繁體轉換（`s2twp.json`）
5. **特殊字元移除：** 移除非文字類符號
6. **全形轉半形：** 全形英數位 → 半形
7. **數字轉換：** 僅轉換「中文數字 + 量詞/單位」結構為阿拉伯數字（例：一百二十三個 → 123 個、三個人 → 3 個人）。成語、固定詞組中的數字不轉換（例：一本萬利、三陽開泰、六六大順 保持不變）。實作建議使用分詞 + 詞性標注（jieba），僅對「CD（數詞）+ MQ（量詞）」結構轉換，避免無差別正規表示式替換誤傷成語。注意：數字轉換排在簡繁轉換之後，確保簡體數字已轉為繁體再處理。
8. **文字正規化：** 統一標點符號格式
9. **同音異字糾錯（可選）：** 基於中文發音規則的同音字替換修正
10. **LLM 語境校正建議（可選）：** 使用 Qwen3 文字模型做語境級校正

**選項控制：** 每個步驟可獨立啟用/停用，透過 API 參數傳遞

**錯誤隔離機制：**
- 每個可選步驟包在 try-except 中，失敗時記錄警告日誌並跳過該步驟
- 不影響後續步驟執行（例如 NEC 失敗不阻擋 KenLM）
- 不影響整體辨識結果回傳（可選步驟全部失敗仍回傳原始 ASR 結果）
- 在 `post_processing` JSONB 欄位記錄哪些步驟成功、哪些跳過、原因為何
- 必要步驟（簡繁轉換、特殊字元移除、全形轉半形、數字轉換）失敗時回傳 HTTP 500

**程式碼結構參考：**
```python
class CorrectionPipeline:
    def correct(self, text: str, options: dict) -> CorrectionResult:
        result = CorrectionResult(text=text, steps_log=[])
        
        # 可選步驟 - 失敗時跳過
        for step in self.optional_steps:
            if options.get(step.name):
                try:
                    result.text = step.process(result.text)
                    result.steps_log.append({"step": step.name, "status": "success"})
                except Exception as e:
                    logger.warning(f"Step {step.name} skipped: {e}")
                    result.steps_log.append({"step": step.name, "status": "skipped", "error": str(e)})
        
        # 必要步驟 - 失敗時拋出異常
        for step in self.required_steps:
            result.text = step.process(result.text)
            result.steps_log.append({"step": step.name, "status": "success"})
        
        return result
```

#### 3.3.6 Fine-tune 訓練管理器 + 校正工作台

**A. 校正工作台（Correction Workflow）：**

**場景：** 使用者只有音檔，沒有正確逐字稿
**流程：**
1. 使用者上傳音檔/影像檔（支援 wav/mp3/mp4/flac/aac/ogg/m4a）
2. 系統自動 ASR + 語者分離（可選）+ 時間軸切分
3. 校正工作台顯示：
   - 音檔播放器（可精確跳到每個時間軸段落）
   - 逐字稿列表（每段含 speaker、start_time、end_time、text）
   - 使用者可逐句編輯、修正文字
4. 校正完成，系統自動生成 JSONL 訓練資料

**Segment 與語者分離的處理規則：**

校正工作台的段落來源依 ASR 輸入時的選項決定：

| 輸入選項 | 段落來源 | 語者標籤 |
|---------|---------|---------|
| ASR + 語者分離 + ForcedAligner | ForcedAligner 的時間戳段落，對齊 pyannote 語者標籤 | 有（SPEAKER_00, SPEAKER_01, ...） |
| ASR + ForcedAligner（無語者分離） | ForcedAligner 的時間戳段落 | 無（統一標記為 UNKNOWN） |
| ASR 僅文字輸出（無 ForcedAligner） | 整段文字作為單一段落 | 無（統一標記為 UNKNOWN） |

**校正時的手動操作：**
- **手動切分段落：** 選取文字區間 → 點擊「切分」→ 選取區間獨立成新段落，時間軸自動等比分割
- **合併段落：** 勾選相鄰段落 → 點擊「合併」→ 文字與時間範圍合併
- **手動指定語者：** 每段卡片的語者標籤可編輯，輸入自訂名稱（例如「主持人」、「來賓 A」）
- **調整時間範圍：** 每段卡片的 start_time / end_time 可手動微調（± 秒級）

**校正工作台 UI 概念：**
三欄布局（音訊區 → 段落清單 → 文字編輯區），詳細版面參閱 4.3 節。
核心互動流程：點擊清單段落 → 波形跳轉 → 自動播放 → 編輯文字 → 防抖儲存。

**自動儲存機制：**
- 防抖自動儲存：使用者停止輸入 2 秒後自動將修改寫入後端
- UI 指示器：顯示「已儲存 / 儲存中 / 未儲存」狀態
- 本地備份：修改內容同時寫入 IndexedDB，網路斷線時資料不遺失
- 網路恢復後自動同步本地備份至後端
- 校正會話支援草稿（draft）狀態持久化

**B. 多格式文件轉換為 JSONL：**

**支援上傳格式：**
| 檔案類型 | 格式 | 轉換邏輯 |
|----------|------|---------|
| 音檔 | wav, mp3, mp4, flac, aac, ogg, m4a | 自動萃取音軌 → ASR → JSONL |
| Excel | xlsx, xls | 欄位映射：音檔路徑 + 逐字稿 → JSONL |
| 字幕檔 | srt, vtt, ass | 時間軸 + 文字 → 配對音檔 → JSONL |
| 純文字 | txt | 逐行/逐段配對音檔 → JSONL |
| CSV | csv | 欄位映射：音檔路徑 + 逐字稿 → JSONL |

**C. 空白範例下載：**
- JSONL 範例：`finetune_example.jsonl`
- Excel 範例：`finetune_template.xlsx`
- CSV 範例：`finetune_template.csv`
- SRT 範例：`finetune_template.srt`

**D. 資料驗證：**
- JSONL 格式校驗、音檔格式檢查、配對完整性
- 音檔時長統計、資料集規模建議

**E. 訓練功能：**
- 支援參數設定、torchrun 多 GPU、loss 記錄、checkpoint 管理
- 早停機制（依據驗證集 WER，預設 patience=3）
- 資料增強管線（背景噪音注入、音高偏移、時間拉伸、響度正規化、環境模擬）

**限制：** 同一時間只能有一個進行中的訓練任務

#### 3.3.7 質檢 WebSocket 接口

**端點：** `ws://host:8000/ws/quality`（與 HTTP API 共用同一 FastAPI 進程，單一端口 8000）
**通訊協議：** JSON 封包
**Uvicorn 配置：** workers=1。WebSocket + HTTP 共用同一進程，多 worker 會導致 WebSocket 連線綁定到單一 worker，造成連線管理複雜。如需水平擴展，V2 升級為 Redis + 多個獨立 Worker 實例。

**階段實作規劃：**
- **Phase 1（批次模式）**：支援完整音檔接收與非同步回傳。
- **Phase 2（串流模式）**：導入 VAD 實時切音與 Qwen3-ASR streaming 推理模式，支援即時音訊串流。

**請求格式：**
```json
{
  "action": "transcribe",
  "audio": "<base64_encoded_audio>",
  "audio_format": "wav",
  "sample_rate": 16000,
  "options": {
    "language": "Chinese",
    "return_timestamps": true,
    "diarization": true,
    "post_processing": true,
    "hotword_group_ids": [1, 2]
  },
  "callback_id": "req_001"
}
```

**回應格式：**
```json
{
  "action": "result",
  "callback_id": "req_001",
  "status": "success",
  "result": {
    "language": "Chinese",
    "text": "...",
    "timestamps": [{"text": "...", "start": 0.1, "end": 0.8}],
    "speakers": [{"speaker": "SPEAKER_00", "start": 0.1, "end": 5.0, "text": "..."}],
    "normalized_text": "..."
  }
}
```

**斷線處理：** 質檢端負責自動重連；Backend 側維持 connection pool。

**WebSocket 認證機制：**

由於瀏覽器原生 WebSocket API **無法**夾帶 `Authorization` header，採用 **Sec-WebSocket-Protocol subprotocol** 方案傳遞 Bearer token：

```
Sec-WebSocket-Protocol: asr.v1, bearer.<base64url(api_key)>
```

- 客戶端建立連線時，將 `bearer.<token>` 作為 subprotocol 之一傳入
- 後端在 `websocket.accept()` 前解析 subprotocol，提取 token 並執行 Argon2id 驗證（與 HTTP Bearer 完全相同的流程）
- 驗證失敗 → 後端回應 HTTP 401 並關閉連線；驗證成功 → 後端回應選定的 subprotocol（必含 `asr.v1`）
- token 不得透過 query string 傳遞（會被 access log、Referer、瀏覽器歷史紀錄洩漏）

**連線後二次驗證（防止 token 過期）：**
- 連線建立後，後端每隔 5 分鐘檢查 `api_keys.expires_at` 與 `is_active`
- 金鑰已過期或被停用 → 主動發送 `{"action": "auth_revoked", "reason": "expired"}` 並關閉連線

**心跳保活機制 (Heartbeat Protocol)：**
- 前端需每隔 30 秒發送 Ping 封包：`{"action": "ping"}`
- 後端收到後立即回覆 Pong 封包：`{"action": "pong", "timestamp": 1715000000}`
- 若後端超過 90 秒未收到該連線的 Ping 封包，必須主動中斷 WebSocket 連線，以避免殭屍連線耗盡系統資源。

**連線識別（多客戶端區分）：**
- 後端為每條 WS 連線分配 `connection_id`（UUID v4），連線建立時回傳 `{"action": "connected", "connection_id": "..."}`
- 後續所有訊息與日誌均以 `(api_key_id, connection_id)` 作為追溯鍵
- 質檢系統可在 `transcribe` 請求中帶 `client_label`（自訂標籤），便於後台識別來源

### 3.4 REST API 端點

#### ASR 辨識
| Method | Path | 說明 | 參數 |
|--------|------|------|------|
| POST | `/api/v1/asr/transcribe` | 離線辨識 | `file`, `model`, `language`, `return_timestamps`, `diarization`, `post_processing`, `vad_enabled`, `denoise_enabled`, `nec_enabled`, `punctuation_enabled`, `hotword_group_ids` |
| GET | `/api/v1/asr/history` | 查詢歷史記錄（keyword 參數使用 PostgreSQL 全文檢索 tsvector/tsquery，非 LIKE 模糊比對） | `page`, `limit`, `source`, `status`, `date_from`, `date_to`, `keyword` |
| GET | `/api/v1/asr/history/:id` | 單一記錄 | - |
| POST | `/api/v1/asr/download/:id` | 下載結果 | format: `json`, `txt`, `srt` |
| GET | `/api/v1/asr/queue` | 查看處理佇列狀態 | `page`, `limit`, `priority` (realtime/batch) |
| POST | `/api/v1/asr/queue/cancel/:id` | 取消佇列中的任務 | - |
| GET | `/api/v1/asr/models` | 可用模型列表 | - |
| POST | `/api/v1/asr/switch-model` | 切換推理模型 | `model_path` |
| POST | `/api/v1/asr/batch` | 批次辨識（多檔同時提交） | `files[]`, 其餘參數同 `/transcribe` |
| GET | `/api/v1/asr/batch/:id` | 批次任務狀態 | - |
| GET | `/api/v1/asr/batch/:id/results` | 批次任務結果（已完成的部分） | `page`, `limit` |

#### ASR 大檔上傳（分片）

當單檔超過 `CHUNKED_UPLOAD_THRESHOLD_MB`（預設 100 MB）時，必須使用分片上傳：

| Method | Path | 說明 | 參數 |
|--------|------|------|------|
| POST | `/api/v1/asr/upload/init` | 初始化分片上傳 | `file_name`, `file_size`, `mime_type`, `total_chunks`, `chunk_size_bytes`, `sha256` |
| PUT | `/api/v1/asr/upload/:upload_id/chunk/:chunk_index` | 上傳單一分片 | binary body + `Content-MD5` header |
| POST | `/api/v1/asr/upload/:upload_id/complete` | 完成上傳並送入辨識 | `transcribe_options` |
| DELETE | `/api/v1/asr/upload/:upload_id` | 取消上傳並清理已上傳分片 | - |
| GET | `/api/v1/asr/upload/:upload_id/status` | 查詢已上傳分片清單與整體進度 | - |

**分片規格：**
- 預設分片大小 10 MB（前端可動態調整 5-20 MB）
- 分片索引從 0 開始連續編號，缺一不可
- 每片透過 `Content-MD5` header 驗證；不符 → 422 `UPLOAD_CHUNK_HASH_MISMATCH`
- `init` 回傳 `upload_id`（UUID v4）與已上傳分片清單（resumable）
- 全部分片上傳完成後，後端合併 + 計算整檔 SHA256 比對 init 提供的值 → 不符直接 fail
- 過期未完成的 upload session 24 小時後自動清理（透過排程清理 `chunked_uploads` 表）

**`chunked_uploads` 暫存表：**

| 欄位 | 類型 | 說明 |
|------|------|------|
| upload_id | UUID PK | 上傳 ID |
| api_key_id | INTEGER FK | 租戶隔離 |
| file_name | VARCHAR(500) | 原始檔名 |
| file_size | BIGINT | 預期檔案大小 |
| expected_sha256 | VARCHAR(64) | 預期整檔 SHA256 |
| total_chunks | INTEGER | 預期分片數 |
| received_chunks | INTEGER[] | 已收到的分片索引 |
| storage_dir | VARCHAR(500) | 分片儲存目錄 |
| status | VARCHAR(30) | `initiated` / `uploading` / `completed` / `cancelled` / `expired` |
| created_at | TIMESTAMP WITH TIME ZONE | - |
| expires_at | TIMESTAMP WITH TIME ZONE | 過期清理時間 |

#### Fine-tune
| Method | Path | 說明 | 參數 |
|--------|------|------|------|
| POST | `/api/v1/finetune/upload` | 上傳訓練資料（JSONL + 音檔） | 多表單上傳 |
| POST | `/api/v1/finetune/upload-batch` | 上傳校正用音檔（wav/mp3/mp4/flac/aac/ogg/m4a） | 多檔案上傳 |
| POST | `/api/v1/finetune/correction/:id` | 啟動校正工作台（ASR+分離） | 回傳 ASR 結果 |
| PUT | `/api/v1/finetune/correction/:session_id/:segment_id` | 校正單段文字 | `corrected_text` |
| GET | `/api/v1/finetune/correction/:session_id` | 取得校正工作台的目前狀態 | - |
| POST | `/api/v1/finetune/correction/:session_id/export` | 導出校正結果為 JSONL | format: `jsonl`, `xlsx`, `csv`, `srt` |
| POST | `/api/v1/finetune/convert` | 上傳文件轉 JSONL（xlsx/srt/txt/csv） | 多表單上傳 + 欄位映射 |
| POST | `/api/v1/finetune/validate` | 驗證訓練資料格式 | 驗證 JSONL 格式、音檔格式、配對完整性 |
| POST | `/api/v1/finetune/tasks` | 建立訓練任務 | `dataset_name`, `base_model`, `parameters` |
| GET | `/api/v1/finetune/tasks` | 列出訓練任務 | `page`, `limit`, `status` |
| GET | `/api/v1/finetune/tasks/:id` | 任務詳情 + 進度 | - |
| GET | `/api/v1/finetune/tasks/:id/loss-chart` | loss 曲線資料 | - |
| POST | `/api/v1/finetune/tasks/:id/cancel` | 取消訓練 | - |
| POST | `/api/v1/finetune/tasks/:id/resume` | 恢復訓練 | - |
| POST | `/api/v1/finetune/tasks/:id/load` | 載入 checkpoint 為推理模型 | `checkpoint_step` |
| DELETE | `/api/v1/finetune/tasks/:id` | 刪除訓練任務 | - |
| GET | `/api/v1/finetune/templates` | 下載空白範例 | format: `jsonl`, `xlsx`, `csv`, `srt` |
| POST | `/api/v1/finetune/datasets/:id/evaluate` | 觸發資料集品質評估 | - |
| GET | `/api/v1/finetune/datasets/:id/quality` | 取得品質報告 | - |

#### Hotword 管理
| Method | Path | 說明 | 參數 |
|--------|------|------|------|
| GET | `/api/v1/hotword/groups` | 列出 hotword 群組 | `page`, `limit`, `is_active` |
| POST | `/api/v1/hotword/groups` | 建立群組 | `group_name`, `description`, `boost_weight` |
| PUT | `/api/v1/hotword/groups/:id` | 更新群組 | `group_name`, `description`, `boost_weight`, `is_active` |
| DELETE | `/api/v1/hotword/groups/:id` | 刪除群組 | - |
| GET | `/api/v1/hotword/groups/:id/words` | 列出群組詞彙 | `page`, `limit` |
| POST | `/api/v1/hotword/groups/:id/words` | 新增詞彙 | `word`, `pronunciation_hint`, `boost_weight` |
| DELETE | `/api/v1/hotword/groups/:id/words/:wid` | 刪除詞彙 | - |
| POST | `/api/v1/hotword/groups/:id/activate` | 啟用群組（下推到解碼器） | - |

#### Dataset 管理（YouTube 下載）
| Method | Path | 說明 | 參數 |
|--------|------|------|------|
| POST | `/api/v1/dataset/youtube/download` | 下載 YouTube 音檔 + 字幕 | `url`（單影片或播放清單） |
| GET | `/api/v1/dataset/youtube/:id` | 下載狀態查詢 | - |
| POST | `/api/v1/dataset/youtube/:id/transcribe` | 觸發 ASR 自動轉錄 | - |
| GET | `/api/v1/dataset/youtube` | 列出下載歷史 | `page`, `limit`, `status` |

#### API 金鑰管理
| Method | Path | 說明 | 參數 |
|--------|------|------|------|
| GET | `/api/v1/auth/keys` | 列出金鑰（不含 hash） | `page`, `limit`, `is_active` |
| POST | `/api/v1/auth/keys` | 建立金鑰（回傳明文字串僅一次） | `name`, `expires_at` |
| PUT | `/api/v1/auth/keys/:id` | 更新金鑰（啟用/停用） | `is_active`, `expires_at` |
| DELETE | `/api/v1/auth/keys/:id` | 刪除金鑰 | - |

#### SSE 事件推送
| Method | Path | 說明 |
|--------|------|------|
| GET | `/api/v1/events` | SSE 事件串流（訓練進度、佇列更新、下載完成） |

**SSE 事件類型：**
| Event Name | 觸發時機 | payload |
|------------|---------|---------|
| `finetune:progress` | 訓練進度變更（epoch 完成、loss 更新） | `task_id`, `epoch`, `loss`, `wer`, `progress_pct` |
| `queue:updated` | 佇列狀態變更（新任務入列、完成、失敗） | `job_id`, `status`, `position` |
| `youtube:download:progress` | YouTube 下載進度更新 | `download_id`, `percent`, `status` |
| `youtube:download:complete` | YouTube 下載完成 | `download_id`, `audio_file_id`, `correction_session_id` |

### 3.5 API 安全與權限隔離機制 (API Security & Tenant Isolation)

為了確保多租戶或跨專案調用時的資料隔離防禦，並防範開發者的人為疏忽（如忘記附加 `WHERE api_key_id = X`），後端必須全面實施依賴注入（Dependency Injection）：
- 必須實作 `get_current_tenant` 的 FastAPI Dependency。
- 所有牽涉到 `transcriptions`, `audio_files`, `correction_sessions`, `finetune_tasks`, `hotword_groups`, `correction_segments` 的業務路由，皆必須透過該 Dependency 強制擷取目前的 `api_key_id`。
- 資料存取層 (Repository / SQLAlchemy) 在構建 Query 時，必須自動掛載 `api_key_id` 過濾條件，禁止開發者自行手動拼接，從根本上防堵 IDOR (越權存取) 漏洞。

### 3.6 統一 API 回應與通訊標準 (API Response & Pagination Standard)

為避免前後端開發過程中的介面對接歧異，所有 REST API 皆必須嚴格遵守以下 JSON 回傳結構：

**成功與錯誤回應標準：**
所有 API 回傳的最外層必須包含 `success` 狀態碼。
- **成功回應：**
  ```json
  {
    "success": true,
    "data": { "任意物件": "..." },
    "error": null
  }
  ```
- **錯誤回應（HTTP 狀態碼非 2xx 時）：**
  ```json
  {
    "success": false,
    "data": null,
    "error": {
      "code": "VALIDATION_FAILED",
      "message": "音檔格式不支援"
    }
  }
  ```

**標準分頁結構 (Pagination)：**
任何帶有 `page` 與 `limit` 參數的列表 API，其 `data` 欄位必須嚴格遵守以下結構，不可由開發者自行發明欄位名稱：
```json
"data": {
  "items": [ {...}, {...} ],
  "pagination": {
    "total": 150,
    "page": 1,
    "limit": 50,
    "total_pages": 3
  }
}
```

**Cursor-based 分頁（大型資料集）：**
辨識歷史等資料量大的清單 API 改用 cursor-based，避免 `OFFSET` 在深層分頁的效能問題：
```json
"data": {
  "items": [ {...}, {...} ],
  "pagination": {
    "next_cursor": "eyJpZCI6MTIzfQ==",
    "has_more": true,
    "limit": 50
  }
}
```
`next_cursor` 為不透明 base64 字串，用戶端原樣回傳即可。

**列表 API 大欄位排除規則：**
列表回應預設**排除**下列 JSONB / TEXT 大欄位，避免單次回應臃腫：
- `transcriptions`：排除 `timestamps`、`speakers`、`post_processing`
- `correction_sessions`：排除 `asr_result`
- `finetune_tasks`：排除 `loss_history`
- `correction_segments`：列表時排除 `original_text` 與 `corrected_text`，僅回傳前 100 字節摘要 + `length`

完整內容需透過詳情 API（單筆 GET）取得。

### 3.6.1 API 版本控管策略

**版本前綴：** 所有 REST 端點必須位於 `/api/v{N}/` 之下，當前主版本為 `v1`。

**版本升級時機（Breaking Change）：**
- 移除既有欄位或路徑
- 重新命名 JSON 欄位
- 修改既有欄位的型別或語意
- 強制要求新的必填欄位
- 變更標準 `success/data/error` 包裝結構

非 breaking change（新增欄位、新增端點、新增 enum 值）保留在 v1。

**棄用週期：**
- 舊版本端點被棄用後，必須在 response header 加入 `Deprecation: true` 與 `Sunset: <RFC1123 date>`
- 最短棄用週期 **6 個月**，期間舊版本仍須維運
- Sunset 日期之後，端點回傳 HTTP 410 Gone

**OpenAPI 並行揭露：** v1 與 v2 並存期間，`/api/v1/docs` 與 `/api/v2/docs` 同時提供。

### 3.6.2 冪等性（Idempotency-Key）

下列「建立資源」型端點**必須支援** `Idempotency-Key` HTTP header：

- `POST /api/v1/asr/transcribe`
- `POST /api/v1/asr/upload/init`
- `POST /api/v1/finetune/upload`
- `POST /api/v1/finetune/tasks`
- `POST /api/v1/dataset/youtube/download`
- `POST /api/v1/hotword/groups`

**運作機制：**
1. 客戶端在 header 帶 `Idempotency-Key: <UUID v4 或 < 64 字元唯一字串>`
2. 後端以 `(api_key_id, idempotency_key, endpoint)` 為唯一鍵儲存於 Redis（V1 可暫用 PostgreSQL `idempotency_records` 表，24 小時 TTL）
3. 同一鍵的請求在 TTL 內：
   - 第一次處理成功 → 儲存 response body + status code
   - 重複請求 → 直接回傳相同 response，不執行業務邏輯
4. 同一鍵但 payload 不同 → 回傳 HTTP 422 `IDEMPOTENCY_KEY_PAYLOAD_MISMATCH`
5. 處理中（尚未完成第一次請求）的鍵 → 回傳 HTTP 409 `IDEMPOTENCY_KEY_IN_PROGRESS`

**TTL：** 預設 24 小時（透過 `IDEMPOTENCY_TTL_HOURS` 環境變數調整）。

**不需冪等性的端點：** GET 請求、DELETE 請求（重複 DELETE 已天然冪等）、PUT 更新（以資源 ID 為唯一鍵）。

---

## 四、前端介面設計

### 4.1 技術棧
- **框架：** Next.js 14 (App Router) + React 18 + TypeScript
- **樣式：** Tailwind CSS
- **圖表：** Recharts（loss 曲線）
- **UI 元件：** Radix UI（無樣式基礎元件）+ 自定義主題
- **音頻播放：** wavesurfer.js（v7+）（波形視覺化、 Regions 外掛、播放控制）
- **WebSocket：** 原生 WebSocket API + reconnect 邏輯
- **伺服器狀態管理：** TanStack Query（v5）（API 資料快取、自動重試、背景輪詢、SSE 整合）
- **UI 狀態管理：** React Context + useReducer（僅處理純前端狀態：表單狀態、展開/收合、選取狀態）
- **本地狀態管理：** Zustand（校正工作台段落編輯、波形同步、IndexedDB 持久化）

**狀態管理完整分工：**
| 類型 | 工具 | 處理範圍 |
|------|------|---------|
| 伺服器狀態 | TanStack Query | API 資料快取、自動重試、背景輪詢、SSE 事件同步 |
| 本地複雜狀態 | Zustand | 校正工作台（數百段落編輯狀態、儲存狀態、IndexedDB 備份）、波形同步（播放時間、高亮段落） |
| 純 UI 狀態 | React Context + useReducer | 表單輸入、側邊欄展開/收合、主題切換 |

**TypeScript 型別同步策略：**
- 後端 FastAPI 自動產生 OpenAPI Schema（`/api/v1/docs`）
- 使用 `openapi-typescript` 將 OpenAPI Schema 轉為 TypeScript 型別定義
- CI 流程中驗證前端型別與後端 Schema 一致性
- 手動維護的型別（SSE 事件、WebSocket 訊息）使用 discriminated union 確保型別安全

**測試策略：**
| 測試類型 | 工具 | 覆蓋範圍 | 覆蓋目標 |
|----------|------|----------|---------|
| 單元測試 | Vitest | hooks（useDebouncedSave、useTranscriptSync）、工具函數（audio-utils） | ≥ 80% |
| 組件測試 | Vitest + React Testing Library | AudioPlayer、TranscriptViewer、CorrectionWorkbench | ≥ 70% |
| 整合測試 | Vitest + MSW | API 請求流程、TanStack Query 快取、SSE 事件處理 | ≥ 60% |
| E2E 測試 | Playwright | 完整辨識流程、校正流程、Fine-tune 流程 | 核心流程 100% |

### 4.2 UI/UX 設計系統：Apple 圓滑風格 (Glassmorphism & Soft UI)

為提供使用者現代、精品且親和的視覺體驗，平台介面全面採用 Apple 經典的圓滑美學 (Glassmorphism & Soft UI)。前端應嚴格遵守以下由 Tailwind CSS 定義的設計參數：

**1. 色彩計畫與毛玻璃特效 (Color & Glass Tokens)**
- **背景色 (Background)**：`#F5F5F7` (Apple Silver Gray) - 取代純白，提供極其乾淨且柔和的底色空間。
- **主視覺色 (Accent)**：`#007AFF` (Apple System Blue) - 用於核心按鈕 (CTA)、文字連結與焦點提示 (Focus Rings)。
- **文字色 (Text)**：`#1D1D1F` (深灰黑) - 取代純黑，降低對比刺眼感。
- **卡片毛玻璃 (Glassmorphism)**：卡片與模態框背景強制使用 `bg-white/70 backdrop-blur-md` 或 `bg-white/80 backdrop-blur-lg`，營造半透明的懸浮層次感。
- **邊框收斂**：在毛玻璃元件外加極細半透明邊框 (`border border-white/40`) 提升邊緣立體高光。

**2. 版面、圓角與陰影 (Shapes & Shadows)**
- **大圓角設計 (Border Radius)**：
  - 卡片、對話框：強制使用 `rounded-2xl` 或 `rounded-3xl`。
  - 按鈕、標籤：強制使用 `rounded-full` (藥丸狀) 或 `rounded-xl`。
- **彌散柔和陰影 (Soft Drop Shadows)**：
  - 禁用生硬的黑色小陰影，改用範圍極大但透明度極低的柔和陰影，例如：`shadow-[0_8px_30px_rgb(0,0,0,0.04)]`。

**3. 字體配對 (Typography)**
- **統一字體**：**`Inter`** (高度還原 Apple San Francisco / SF Pro 的無襯線字體，提供極致流暢的閱讀體驗)。
- **排版層級**：捨棄多種字體混用，純粹依靠 `Inter` 的粗細 (如 Font Weight 400, 500, 600) 來劃分標題與內文層級。
- *請透過 Google Fonts 引入：`family=Inter:wght@300;400;500;600;700`*

**4. 前端交付 UX 檢核清單 (Pre-Delivery Checklist)**
前端工程師在提交 PR 前，必須確保所有元件符合以下無障礙與互動標準：
- [ ] **視覺圖示**：嚴禁使用 Emoji 作為 UI 圖示，強制使用 Lucide 或 Heroicons 的流線型 SVG。
- [ ] **物理彈簧互動**：Hover 動畫應加入輕微縮放搭配平滑過渡（如 `hover:scale-[1.02] transition-transform duration-300 ease-out`），模擬 iOS 的物理彈性回饋。
- [ ] **互動回饋**：所有可點擊元件（按鈕、卡片、清單項）必須加上 `cursor-pointer`。
- [ ] **無障礙對比度**：確保文字與淺灰色背景/毛玻璃背景之間的對比度符合最低 4.5:1 (WCAG AA 標準)。
- [ ] **鍵盤導航**：Focus 狀態必須加上 `#007AFF` 顏色的 Focus Ring（例如 `focus:ring-2 focus:ring-blue-500/50`）。

### 4.3 版面規劃

#### 設計原則：無頁面級捲軸

**核心原則：** 整個應用在單一 viewport 內完整呈現，不產生頁面級（body/html）捲軸。各功能區域獨立捲動。

#### 全域 Layout 結構

```
┌─────────────────────────────────────────────────────────────┐
│  Header (48px) - 固定高度                                    │
│  [Logo] Qwen3-ASR                    [GPU狀態] [佇列狀態]    │
├──────────┬──────────────────────────────────────────────────┤
│          │  Main Content (flex: 1, overflow: hidden)        │
│  Side    │  ┌────────────────────────────────────────────┐  │
│  Nav     │  │  Page Content (overflow-y: auto)           │  │
│  (240px) │  │                                            │  │
│  固定    │  │  各頁面的可捲動內容區域                     │  │
│          │  │                                            │  │
│          │  │                                            │  │
│          │  └────────────────────────────────────────────┘  │
└──────────┴──────────────────────────────────────────────────┘
```

**CSS 佈局策略：**
```css
/* globals.css */
html, body {
  height: 100vh;
  overflow: hidden;  /* 禁止頁面級捲軸 */
}

#root {
  height: 100vh;
  display: flex;
  flex-direction: column;
}

/* 全域 layout */
.app-layout {
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
}

.app-header {
  height: 48px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  padding: 0 16px;
  border-bottom: 1px solid #2a2a2a;
}

.app-body {
  display: flex;
  flex: 1;
  overflow: hidden;
}

.app-sidebar {
  width: 240px;
  flex-shrink: 0;
  border-right: 1px solid #2a2a2a;
  overflow-y: auto;  /* 側邊欄獨立捲動（選單多時） */
}

.app-main {
  flex: 1;
  overflow: hidden;  /* 主區域不捲動，由各頁面自行控制 */
}
```

#### 各頁面版面配置

##### 離線辨識主頁 `(/)`

```
┌──────────────────────────────────────────────────────────────┐
│  Main Content (height: calc(100vh - 48px), overflow: hidden) │
│  ┌──────────────────────────────────────────────────────────┐│
│  │  上傳區域 (flex-shrink: 0, 固定高度 120px)               ││
│  │  [拖拉上傳音檔] [選擇檔案] [Hotword 群組選擇]            ││
│  ├──────────────────────────────────────────────────────────┤│
│  │  波形播放器 (flex-shrink: 0, 固定高度 180px)             ││
│  │  [wavesurfer.js 波形] [播放控制] [時間顯示]              ││
│  ├──────────────────────────────────────────────────────────┤│
│  │  逐字稿區域 (flex: 1, overflow-y: auto)                  ││
│  │  ┌────────────────────────────────────────────────────┐  ││
│  │  │ SPEAKER_00 [00:01 - 00:05] 這是辨識結果...         │  ││
│  │  │ SPEAKER_01 [00:06 - 00:12] 另一段辨識結果...       │  ││
│  │  │ ...（獨立捲動）                                     │  ││
│  │  └────────────────────────────────────────────────────┘  ││
│  └──────────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────────┘
```

**CSS：**
```css
.asr-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.upload-area { flex-shrink: 0; height: 120px; }
.waveform-area { flex-shrink: 0; height: 180px; }
.transcript-area { flex: 1; overflow-y: auto; }
```

##### 校正工作台 `(/finetune/correction/[id])`

**Fine-tune 校正流程對應：** 音檔上傳 → ASR 自動轉錄 → 逐段聽音校正 → 匯出 JSONL → 資料集品質評估 → 訓練

**三欄布局：音訊 → 清單 → 編輯**

```
┌─────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│  Main Content (height: calc(100vh - 48px), overflow: hidden)                                            │
│  ┌──────────────────┬──────────────────────┬──────────────────────────────────────────────────────────┐│
│  │  A. 音訊區       │  B. 段落清單          │  C. 文字編輯區                                          ││
│  │  (320px 固定)    │  (280px 固定)         │  (flex: 1, overflow-y: auto)                            ││
│  │                  │                      │                                                          ││
│  │  ┌──────────────┐│  ┌────────────────┐ │  ┌────────────────────────────────────────────────────┐  ││
│  │  │ 波形播放器   ││  │ 搜尋 / 篩選    │ │  │ ┌────────────────────────────────────────────────┐ │  ││
│  │  │ wavesurfer.js││  │ [搜尋文字]     │ │  │ │ SPEAKER_00  [00:01.2 - 00:05.8]  [▶ 播放]     │ │  ││
│  │  │ 160px        ││  ├────────────────┤ │  │ ├────────────────────────────────────────────────┤ │  ││
│  │  │              ││  │ SPEAKER_00     │ │  │ │ 原文：這是錯誤的辨識文字                       │ │  ││
│  │  │ [▶] [◀◀] [▶▶]││  │ 00:01-00:05  ✓│ │  │ │                                              │ │  ││
│  │  │ [0.5x][1x]   ││  │ [已校正]       │ │  │ │ 校正：這是正確的辨識文字 [已儲存 ✓]             │ │  ││
│  │  └──────────────┘│  │                │ │  │ │ [◀ 上一段] [下一段 ▶]                        │ │  ││
│  │                  │  │ SPEAKER_01     │ │  │ └────────────────────────────────────────────────┘ │  ││
│  │  播放控制        │  │ 00:06-00:12  ●│ │  │                                                          ││
│  │  ┌──────────────┐│  │ [編輯中]       │ │  │ ┌────────────────────────────────────────────────┐ │  ││
│  │  │ 當前段落     ││  │                │ │  │ │ SPEAKER_01  [00:06.0 - 00:12.3]  [▶ 播放]     │ │  ││
│  │  │ 語者 | 時間  ││  │ SPEAKER_00     │ │  │ ├────────────────────────────────────────────────┤ │  ││
│  │  │ 快速跳轉     ││  │ 00:13-00:18    │ │  │ │ 原文：另一句錯誤文字                           │ │  ││
│  │  └──────────────┘│  │ [未校正 ⚠]     │ │  │ │                                              │ │  ││
│  │                  │  │                │ │  │ │ 校正：[文字框 - 焦點在此]                     │ │  ││
│  │  統計資訊        │  │ ...            │ │  │ │ [◀ 上一段] [下一段 ▶]                        │ │  ││
│  │  ┌──────────────┐│  │                │ │  │ └────────────────────────────────────────────────┘ │  ││
│  │  │ 總段落：156  ││  │ ...（獨立捲動）│ │  │                                                          ││
│  │  │ 已校正：128  ││  │                │ │  │ ...（更多段落，獨立捲動）                              ││
│  │  │ 未校正：28   ││  │ 底部統計列     │ │  └────────────────────────────────────────────────────┘  ││
│  │  │ 跳過：0      ││  │ ──────────────│ │                                                          ││
│  │  └──────────────┘│  │ 已校正 82% ■■■│ │  [全部儲存] [匯出 JSONL] [匯出 Excel] [品質評估]         ││
│  │                  │  └────────────────┘ │                                                          ││
│  └──────────────────┴──────────────────────┴──────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

**各區域功能說明：**

**A. 音訊區（左欄，320px 固定）：**
- **波形播放器：** wavesurfer.js 顯示完整音檔波形，Regions 外掛標記語者分段（不同色彩）
- **反覆聽音檔機制：**
  - **單段循環：** 當前段落播完自動回到該段起點重播，持續到使用者手動停止或切換段落
  - **自訂循環區間：** 在波形上拖曳選取任意時間區間（例如某兩秒），僅循環播放該區間；解除選取後恢復單段循環
  - **播放速度快捷切換：** 按鈕列（0.5x/0.75x/1x/1.25x/1.5x/2x），鍵盤數字鍵 1-6 即時切換，不需停止播放
  - **波形點擊跳轉：** 點擊波形任意位置立即跳轉到該時間點
  - **當前段落波形放大：** 切換段落時，波形自動 zoom 到當前段落的时间範圍，方便精確定位
- **播放控制：** 播放/暫停、上一段、下一段、循環開關、循環區間設定
- **當前段落資訊：** 顯示目前焦點段落的語者、時間範圍、快速跳轉按鈕
- **統計資訊：** 總段落數、已校正、未校正、跳過（即時更新）

**B. 段落清單（中欄，280px 固定）：**
- **搜尋/篩選：** 依文字內容搜尋、依語者篩選、依狀態篩選（已校正/未校正/跳過）
- **段落列表：** 每筆顯示語者標籤、時間範圍、狀態指示器（✓ 已校正 / ● 編輯中 / ⚠ 未校正）
- **點擊行為：** 點擊段落 → 波形跳轉到該段開始時間 → 右欄載入該段編輯區 → 自動播放該段
- **底部統計列：** 校正進度條（百分比 + 視覺化）

**C. 文字編輯區（右欄，flex: 1）：**
- **段落卡片：** 每段獨立卡片，包含：
  - 標頭：語者標籤、時間範圍、播放按鈕（點擊僅播該段，自動進入單段循環）
  - **原文 / 校正比對布局：**
    - 上下排列：原文區在上（唯讀，淺灰色背景，13px），校正區在下（可編輯，深色背景，15px）
    - 原文區使用等寬字體，方便逐字比對
    - 校正區使用一般字體，輸入舒適度優先
    - 長段落自動換行（word-wrap），行高 1.6，確保可讀性
  - **diff 高亮：** 校正文字與原文不同的部分以淺色底標記（類似 git diff），方便快速確認修改處
  - **聚焦模式：** 點擊卡片進入編輯時，該卡片放大至全欄寬度，其他卡片縮減為時間軸縮略圖，減少視覺干擾；點擊卡片外區域退出聚焦模式
  - 狀態指示器：已儲存 ✓ / 儲存中 / 未儲存
  - 導航按鈕：上一段 / 下一段（支援鍵盤 ← → 切換）
- **虛擬滾動：** 段落數 > 100 時啟用 @tanstack/react-virtual，只渲染可見區域
- **底部工具列：** 全部儲存、匯出 JSONL、匯出 Excel、觸發資料集品質評估

**鍵盤快捷鍵：**
| 快捷鍵 | 功能 |
|--------|------|
| 空白鍵 | 播放/暫停當前段落 |
| ← / → | 上一段 / 下一段 |
| Ctrl + S | 手動觸發儲存 |
| Ctrl + Enter | 跳到下一段並自動儲存 |
| Ctrl + F | 聚焦搜尋框 |
| Home / End | 跳到第一/最後一個段落 |
| Escape | 取消編輯，回到唯讀模式 |

**CSS：**
```css
.correction-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.correction-body {
  display: flex;
  flex: 1;
  overflow: hidden;
}

/* A. 音訊區 */
.correction-audio {
  width: 320px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  border-right: 1px solid #2a2a2a;
  overflow: hidden;
}
.correction-waveform { flex-shrink: 0; height: 160px; }
.correction-controls { flex-shrink: 0; padding: 8px; }
.correction-current { flex-shrink: 0; padding: 8px; }
.correction-stats { flex-shrink: 0; padding: 8px; }

/* B. 段落清單 */
.correction-list {
  width: 280px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  border-right: 1px solid #2a2a2a;
  overflow: hidden;
}
.correction-list-search { flex-shrink: 0; padding: 8px; }
.correction-list-items { flex: 1; overflow-y: auto; }
.correction-list-stats { flex-shrink: 0; padding: 8px; border-top: 1px solid #2a2a2a; }

/* C. 文字編輯區 */
.correction-editor {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}
.correction-card {
  /* 段落卡片樣式 */
  margin-bottom: 12px;
  border: 1px solid #2a2a2a;
  border-radius: 4px;
}
.correction-card:focus-within {
  border-color: #3b82f6;  /* 焦點卡片高亮 */
}
.correction-toolbar {
  position: sticky;
  bottom: 0;
  background: #1a1a1a;
  padding: 8px 16px;
  border-top: 1px solid #2a2a2a;
  display: flex;
  gap: 8px;
}
```

##### Fine-tune 訓練管理 `(/finetune/training)`

```
┌──────────────────────────────────────────────────────────────┐
│  Main Content (height: calc(100vh - 48px), overflow: hidden) │
│  ┌──────────────────────────────────────────────────────────┐│
│  │  工具列 (flex-shrink: 0, 固定高度 48px)                  ││
│  │  [建立任務] [資料集選擇] [搜尋]                          ││
│  ├──────────────────────────────────────────────────────────┤│
│  │  任務列表 (flex: 1, overflow-y: auto)                    ││
│  │  ┌────────────────────────────────────────────────────┐  ││
│  │  │ 任務名稱 | 狀態 | 進度 | Loss | 操作               │  ││
│  │  │ ...（獨立捲動）                                     │  ││
│  │  └────────────────────────────────────────────────────┘  ││
│  └──────────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────────┘
```

##### 任務詳情 `(/finetune/training/[id])`

```
┌──────────────────────────────────────────────────────────────┐
│  Main Content (height: calc(100vh - 48px), overflow: hidden) │
│  ┌──────────────────────────────────────────────────────────┐│
│  │  工具列 (flex-shrink: 0) [← 返回] [取消] [載入模型]     ││
│  ├──────────────────────────────────────────────────────────┤│
│  │  Loss 曲線 (flex-shrink: 0, height: 240px)              ││
│  │  [Recharts 圖表]                                         ││
│  ├──────────────────────────────────────────────────────────┤│
│  │  訓練日誌 (flex: 1, overflow-y: auto)                    ││
│  │  ┌────────────────────────────────────────────────────┐  ││
│  │  │ [epoch 1] loss: 0.123, wer: 0.045                 │  ││
│  │  │ ...（獨立捲動）                                     │  ││
│  │  └────────────────────────────────────────────────────┘  ││
│  └──────────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────────┘
```

##### 辨識歷史 `(/history)`

```
┌──────────────────────────────────────────────────────────────┐
│  Main Content (height: calc(100vh - 48px), overflow: hidden) │
│  ┌──────────────────────────────────────────────────────────┐│
│  │  搜尋/篩選列 (flex-shrink: 0, 固定高度 48px)             ││
│  │  [關鍵字搜尋] [日期範圍] [狀態篩選] [來源篩選]           ││
│  ├──────────────────────────────────────────────────────────┤│
│  │  歷史列表 (flex: 1, overflow-y: auto, 虛擬滾動)          ││
│  │  ┌────────────────────────────────────────────────────┐  ││
│  │  │ 檔名 | 語言 | 時長 | 狀態 | 時間 | 操作            │  ││
│  │  │ ...（虛擬滾動渲染）                                  │  ││
│  │  └────────────────────────────────────────────────────┘  ││
│  └──────────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────────┘
```

##### 質檢管理 `(/quality)`

```
┌──────────────────────────────────────────────────────────────┐
│  Main Content (height: calc(100vh - 48px), overflow: hidden) │
│  ┌──────────────────────────────────────────────────────────┐│
│  │  狀態列 (flex-shrink: 0) [WS連線狀態] [佇列深度]        ││
│  ├──────────────────────────────────────────────────────────┤│
│  │  日誌區域 (flex: 1, overflow-y: auto)                    ││
│  │  ┌────────────────────────────────────────────────────┐  ││
│  │  │ [timestamp] [level] [message]                      │  ││
│  │  │ ...（獨立捲動）                                     │  ││
│  │  └────────────────────────────────────────────────────┘  ││
│  └──────────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────────┘
```

#### 側邊欄導航

```
側邊欄選單：
┌─────────────────┐
│ 🎙 離線辨識     │
│ 📝 辨識歷史     │
│ 🔧 Fine-tune    │
│   ├ 校正工作台  │
│   ├ 資料集管理  │
│   ├ 訓練管理    │
│   ├ Hotword     │
│   └ YouTube     │
│ 📊 質檢管理     │
└─────────────────┘

- 寬度：240px（可收合為 64px 圖示模式）
- 收合狀態：僅顯示圖示，hover 展開完整選單
- 獨立 overflow-y: auto（選單項目多時獨立捲動）
```

#### 響應式斷點

| 斷點 | 螢幕寬度 | 行為 |
|------|---------|------|
| desktop | ≥ 1280px | 雙欄布局（校正工作台），側邊欄展開 |
| tablet | 768-1279px | 單欄布局，側邊欄收合為圖示 |
| mobile | < 768px | 不強求完整支援，側邊欄為抽屜式（drawer） |

#### 捲軸樣式統一

所有獨立捲動區域使用自訂捲軸樣式（深色主題）：

```css
/* 自訂捲軸 */
::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

::-webkit-scrollbar-track {
  background: #1a1a1a;
}

::-webkit-scrollbar-thumb {
  background: #3a3a3a;
  border-radius: 4px;
}

::-webkit-scrollbar-thumb:hover {
  background: #4a4a4a;
}
```

### 4.4 頁面設計

#### 離線辨識主頁 `(/)`

**功能細節：**
- 支援多檔同時上傳，逐一處理後合併展示
- 辨識結果支援全文搜尋
- 時間軸與播放器同步（點播、逐字高亮）
- 語者分段以不同色彩區分
- 後處理開關即時預覽效果
- 匯出支援 SRT（時間軸字幕格式）
- Hotword 群組選擇器
- **音檔取樣率回饋：** 上傳後顯示原始取樣率；8kHz 音檔顯示警示「取樣率偏低，辨識準確率可能受限」；重取樣完成後顯示「已重取樣至 16kHz」

**音檔上傳卡片顯示資訊：**
```
┌────────────────────────────────────────────────────────┐
│  meeting_20260515.wav                                  │
│  原始取樣率：8kHz ⚠️ 取樣率偏低，辨識準確率可能受限       │
│  狀態：已重取樣至 16kHz ✓                              │
│  時長：12:34 | 大小：12.4 MB                           │
│  [開始辨識] [移除]                                     │
└────────────────────────────────────────────────────────┘
```

**AudioPlayer 功能規格：**
- 波形視覺化：使用 wavesurfer.js（v7+）渲染音檔波形
- 播放速度：0.5x / 0.75x / 1x / 1.25x / 1.5x / 2x
- 進度條：可拖曳，即時顯示當前時間 / 總時長
- 鍵盤快捷鍵：空白鍵（播放/暫停）、← →（前後 5 秒）、↑ ↓（音量）
- 音量控制：滑桿 + 靜音切換
- 循環播放：單段循環（校正工作台使用）
- 雙向同步：播放時 TranscriptViewer 自動滾動高亮；點擊文字段落跳轉音檔
- 語者分段標記：波形上以不同色彩區間顯示語者分段（wavesurfer Regions 外掛）

#### 質檢管理頁 `(/quality)`

**使用者定位：** 平台管理員與系統監控用。外部質檢系統透過 WebSocket API 程式對接（不需此頁面），此頁面供管理員監控平台運行狀態。

**功能：**
- **WS 連線狀態：** 目前連線數、各連線的 IP 與連線時間、訊息吞吐量
- **佇列管理：** 待處理數量、目前處理中任務、預估等待時間、手動取消任務
- **處理日誌：** 即時日誌串流（可篩選等級：INFO/WARNING/ERROR）、錯誤統計
- **GPU 狀態：** VRAM 使用量、溫度、目前載入的模型列表

#### Fine-tune 管理頁

**採用 Next.js 子路由架構（非 Tab 式布局）：**

| 路由 | 頁面 | 功能 |
|------|------|------|
| `/finetune/correction` | 校正列表 | 校正會話列表（上傳新音檔、歷史會話列表） |
| `/finetune/correction/[session_id]` | 校正工作台 | 單次校正會話（編輯、儲存、匯出） |
| `/finetune/datasets` | 資料集管理 | 資料集列表、品質評估、多格式轉換 |
| `/finetune/training` | 訓練管理 | 任務列表、Loss 曲線、參數設定 |
| `/finetune/training/[task_id]` | 任務詳情 | 單一訓練任務進度、Loss 曲線、參數 |
| `/finetune/hotwords` | Hotword 管理 | 群組建立、詞彙增刪、啟用/停用 |
| `/finetune/youtube` | YouTube 下載 | URL 輸入、下載進度、自動進入校正流程 |

**導航設計：** 側邊欄或頂部 Tab 導航使用 `next/link` 對應各子路由
**好處：** URL 可分享、瀏覽器前後鍵正常運作、各頁面可獨立 SSR/Client Component 配置

**Fine-tune 完整頁面跳轉流程：**

```
方式 A：手動上傳音檔
  /finetune/correction（列表頁）
    → 上傳音檔
    → 後端 ASR + 語者分離
    → 自動跳轉 /finetune/correction/[session_id]（校正工作台）
    → 使用者逐段校正
    → 點擊「匯出 JSONL」
    → 跳轉 /finetune/datasets（資料集管理，新資料集已加入列表）
    → 選擇資料集 → 點擊「建立訓練任務」
    → 跳轉 /finetune/training（任務列表，新任務已建立）
    → 點擊任務 → /finetune/training/[task_id]（監控訓練進度）

方式 B：YouTube 下載
  /finetune/youtube
    → 輸入 URL → 下載完成
    → 自動觸發 ASR
    → 自動跳轉 /finetune/correction/[session_id]（校正工作台，字幕作為初始參考）
    → 後續同方式 A

方式 C：多格式轉換
  /finetune/datasets
    → 上傳 xlsx/srt/txt/csv
    → 欄位映射 → 轉換為 JSONL
    → 資料集直接加入列表（不需校正，因已有正確逐字稿）
    → 點擊「建立訓練任務」
    → 跳轉 /finetune/training
```

#### 辨識歷史頁 `(/history)`

**功能：** 搜尋、篩選、查看離線辨識歷史

| 路由 | 頁面 | 功能 |
|------|------|------|
| `/history/[id]` | 歷史詳情 | 單一辨識記錄詳情（逐字稿、時間軸、語者） |

### 4.5 專案結構

```
frontend/
  app/
    layout.tsx                    # 全域佈局 + 深色主題 + 導航
    page.tsx                      # 離線辨識主頁
    quality/
      page.tsx                    # 質檢管理頁
    finetune/
      layout.tsx                    # Fine-tune 全域佈局（側邊導航）
      correction/
        page.tsx                    # 校正工作台
      datasets/
        page.tsx                    # 資料集管理
      training/
        page.tsx                    # 訓練管理
      hotwords/
        page.tsx                    # Hotword 管理
      youtube/
        page.tsx                    # YouTube 下載
    history/
      page.tsx                    # 辨識歷史頁
  components/
    layout/
      Sidebar.tsx                 # 側邊導航
      Header.tsx
    asr/
      AudioUploader.tsx           # 音檔上傳組件
      SettingsPanel.tsx           # 參數設定面板
      TranscriptViewer.tsx        # 逐字稿展示
      TimelineViewer.tsx          # 時間軸波形視圖
      SpeakerSegments.tsx         # 語者分段視圖
      AudioPlayer.tsx             # 音檔播放器
      ExportButtons.tsx           # 匯出按鈕
      HotwordSelector.tsx         # Hotword 群組選擇器
    finetune/
      TaskManager.tsx             # 任務列表
      LossChart.tsx               # loss 曲線圖表
      DatasetUploader.tsx         # 資料上傳
      ParametersForm.tsx          # 訓練參數表單
      CorrectionWorkbench.tsx     # 校正工作台
      FileConverter.tsx           # 多格式轉換
      TemplateDownloader.tsx      # 範例下載
      HotwordManager.tsx          # Hotword 管理
      YouTubeDownloader.tsx       # YouTube 下載
      DatasetQualityDashboard.tsx # 資料集品質儀表板
    quality/
      WSStatus.tsx                # WS 連線狀態
      QueueTable.tsx              # 佇列表格
      LogViewer.tsx               # 日誌查看器
    history/
      SearchBar.tsx
      HistoryTable.tsx
    ui/                           # 共用 UI 基礎元件（基於 Radix UI）
      Button.tsx
      Input.tsx
      Textarea.tsx                # 校正文字編輯
      Select.tsx
      Card.tsx
      Modal.tsx                   # 含 focus trap
      Toast.tsx
      ProgressBar.tsx             # 上傳進度、訓練進度
      Badge.tsx                   # 狀態標籤（processing/completed/failed）
      Tabs.tsx                    # Fine-tune 頁面導航
      DataTable.tsx               # 通用表格（含排序、篩選）
      Tooltip.tsx
      Skeleton.tsx                # 載入骨架屏
      DropdownMenu.tsx
      Checkbox.tsx
  hooks/
    use-audio-player.ts       # 播放器狀態管理（Zustand store hook）
    use-transcript-sync.ts    # 波形 ↔ 逐字稿雙向同步
    use-correction-session.ts # 校正工作台狀態（段落編輯、自動儲存、IndexedDB）
    use-sse.ts                # SSE 事件訂閱（EventSource 封裝）
    use-websocket.ts          # WebSocket 連線管理（自動重連、心跳）
    use-debounced-save.ts     # 防抖自動儲存（2 秒 delay）
    use-virtual-list.ts       # 虛擬滾動（@tanstack/react-virtual 封裝）
  lib/
    api.ts                    # API 請求工具（含 retry、error interceptor）
    websocket.ts              # WebSocket 封裝
    types/                    # TypeScript 型別（按模組拆分）
      index.ts                # 匯出
      asr.ts                  # TranscriptionResult, TimeStamp, SpeakerSegment
      finetune.ts             # FinetuneTask, LossPoint, DatasetQuality
      correction.ts           # CorrectionSession, CorrectionSegment
      hotword.ts              # HotwordGroup, Hotword
      youtube.ts              # YouTubeDownload
      sse.ts                  # SSEEvent（discriminated union）
      websocket.ts            # WSMessage, WSAction（discriminated union）
      ui.ts                   # Theme, ToastType
    audio-utils.ts            # 音檔工具函數（格式檢查、大小限制、取樣率偵測）
  styles/
    globals.css                   # 全域 CSS + 主題變數
  public/
    (靜態資源)
  next.config.ts
  tsconfig.json
  docker/
    Dockerfile
  package.json
```

### 4.6 效能策略

#### 大檔案上傳
- 使用 XMLHttpRequest（非 fetch）取得上傳進度事件
- 大檔（> 100 MB）分片上傳：每片 10 MB，失敗僅重傳該片
- 前端預檢：File API 檢查 MIME type 與大小；AudioContext 僅讀取檔案頭部（不解碼全檔，避免 500 MB 音檔 OOM）

#### 虛擬滾動
- TranscriptViewer：20 分鐘音檔可能產生 500+ 段落，使用 @tanstack/react-virtual 只渲染可見區域（約 20-30 個段落）
- 辨識歷史頁：useInfiniteQuery（cursor-based 分頁，每頁 50 筆）+ 虛擬滾動，滾動至距底部 10 筆時 prefetch 下一頁

#### SSE 事件 Throttle
- YouTube 下載進度：每秒最多更新 10 次（100 ms throttle）
- Fine-tune loss 曲線：每秒最多更新 6 次（167 ms throttle），使用 requestAnimationFrame 批次處理
- 佇列更新：即時推送（頻率低，不需 throttle）

#### Lazy Loading
- wavesurfer.js：使用 next/dynamic 延遲載入，僅在主頁和校正工作台載入
- Recharts：使用 next/dynamic 延遲載入，僅在訓練管理頁載入
- Route-level code splitting：Next.js App Router 預設支援，每個 top-level route 獨立 chunk

#### Bundle Size 監控
- 使用 @next/bundle-analyzer 監控 bundle 大小
- 目標：初始 bundle（不含 lazy load）< 150 KB gzip

---

## 五、資料庫設計

### 5.1 transcriptions（辨識歷史表）

| 欄位 | 類型 | 說明 |
|------|------|------|
| id | SERIAL PK | 主鍵 |
| api_key_id | INTEGER FK | 關聯 api_keys（資料隔離） |
| file_name | VARCHAR(500) | 原始音檔名稱 |
| source | VARCHAR(50) | 來源：`upload` 或 `quality_ws` |
| duration_sec | FLOAT | 音檔時長（秒） |
| language | VARCHAR(20) | 偵測/指定語言 |
| model_name | VARCHAR(100) | 使用的模型名稱 |
| model_version | VARCHAR(50) | 模型版本編號（用於切換時追溯） |
| transcript_text | TEXT | 原始逐字稿 |
| timestamps | JSONB | 時間戳資料 `[{"text","start","end"}]` |
| speakers | JSONB | 語者分段 `[{"speaker","start","end","text"}]` |
| normalized_text | TEXT | 後處理後文字 |
| post_processing | JSONB | 使用的後處理選項 |
| status | VARCHAR(50) | `processing` / `completed` / `failed` |
| processing_duration_sec | FLOAT | 實際處理耗時（秒） |
| error_message | TEXT | 錯誤訊息 |
| hotword_group_ids | INTEGER[] | 辨識時使用的 hotword 群組 ID 陣列 |
| created_at | TIMESTAMP WITH TIME ZONE | 建立時間（UTC 儲存，應用層依使用者時區呈現） |
| updated_at | TIMESTAMP WITH TIME ZONE | 更新時間（UTC） |

### 5.2 finetune_tasks（訓練任務表）

| 欄位 | 類型 | 說明 |
|------|------|------|
| id | SERIAL PK | 主鍵 |
| api_key_id | INTEGER FK | 關聯 api_keys（資料隔離） |
| task_name | VARCHAR(200) | 任務名稱 |
| base_model | VARCHAR(100) | 基礎模型 |
| dataset_id | INTEGER FK NOT NULL | 關聯 datasets（5.10 節） |
| parameters | JSONB | 訓練參數 |
| checkpoint_dir | VARCHAR(500) | Checkpoint 目錄（實際 checkpoint 紀錄於 finetune_checkpoints 表） |
| process_pid | INTEGER NULL | 訓練子行程 PID（用於取消時的 SIGTERM/SIGKILL） |
| status | VARCHAR(50) | `pending` / `training` / `completed` / `failed` / `cancelled` |
| progress_pct | INTEGER | 完成百分比 |
| current_epoch | INTEGER | 當前 epoch |
| total_epochs | INTEGER | 總 epochs |
| current_loss | FLOAT | 當前 loss |
| loss_history | JSONB | loss 記錄 `[{epoch, loss}]` |
| best_checkpoint_id | INTEGER FK NULL | 關聯 finetune_checkpoints 最佳節點 |
| is_active | BOOLEAN | 是否為當前推理模型 |
| learning_rate | FLOAT | 學習率 |
| batch_size | INTEGER | 批次大小 |
| patience | INTEGER | 早停 patience |
| best_wer | FLOAT | 最佳驗證集 WER |
| validation_split | FLOAT DEFAULT 0.1 | 驗證集比例 |
| error_message | TEXT | 錯誤訊息 |
| created_at | TIMESTAMP WITH TIME ZONE | 建立時間（UTC 儲存，應用層依使用者時區呈現） |
| updated_at | TIMESTAMP WITH TIME ZONE | 更新時間（UTC） |

### 5.3 audio_files（音檔記錄表）

| 欄位 | 類型 | 說明 |
|------|------|------|
| id | SERIAL PK | 主鍵 |
| api_key_id | INTEGER FK | 關聯 api_keys（資料隔離） |
| original_name | VARCHAR(500) | 原始檔名 |
| storage_path | VARCHAR(500) | 儲存路徑 |
| file_size | BIGINT | 檔案大小 |
| duration_sec | FLOAT | 時長 |
| mime_type | VARCHAR(50) | MIME 類型（來自請求 header，不可信） |
| verified_mime_type | VARCHAR(50) | MIME 類型（magic bytes 檢測結果，可信） |
| transcription_id | INTEGER FK | 關聯辨識記錄 |
| original_sample_rate | INTEGER | 原始取樣率（Hz） |
| created_at | TIMESTAMP WITH TIME ZONE | 建立時間（UTC 儲存，應用層依使用者時區呈現） |

### 5.4 correction_sessions（校正工作會話表）

| 欄位 | 類型 | 說明 |
|------|------|------|
| id | SERIAL PK | 主鍵 |
| api_key_id | INTEGER FK | 關聯 api_keys（資料隔離） |
| session_id | UUID | 會話 UUID |
| audio_file_id | INTEGER FK | 關聯 audio_files |
| asr_result | JSONB | ASR 原始結果（含時間軸、語者） |
| status | VARCHAR(50) | `draft` / `completed` / `exported` |
| export_format | VARCHAR(20) | 匯出格式 |
| created_at | TIMESTAMP WITH TIME ZONE | 建立時間（UTC 儲存，應用層依使用者時區呈現） |
| updated_at | TIMESTAMP WITH TIME ZONE | 更新時間（UTC） |

**校正段落資料儲存於 5.5 節的 correction_segments 獨立表，避免 JSONB 欄位並發編輯時的 race condition。**

### 5.5 correction_segments（校正段落表）

| 欄位 | 類型 | 說明 |
|------|------|------|
| id | SERIAL PK | 主鍵 |
| api_key_id | INTEGER FK | 關聯 api_keys（資料隔離） |
| session_id | INTEGER FK | 關聯 correction_sessions |
| segment_index | INTEGER | 段落順序索引 |
| start_time | FLOAT | 開始時間（秒） |
| end_time | FLOAT | 結束時間（秒） |
| speaker | VARCHAR(50) | 語者標籤 |
| original_text | TEXT | ASR 原始文字 |
| corrected_text | TEXT | 校正後文字 |
| is_modified | BOOLEAN DEFAULT false | 是否已被修改 |
| version | INTEGER NOT NULL DEFAULT 1 | optimistic locking 版本號，每次 UPDATE 自增 |
| last_modified_by | INTEGER FK NULL | 最後修改者金鑰 ID |
| created_at | TIMESTAMP WITH TIME ZONE | 建立時間（UTC 儲存，應用層依使用者時區呈現） |
| updated_at | TIMESTAMP WITH TIME ZONE | 更新時間（UTC） |

**設計理由：** 將校正段落從 JSONB 獨立為關聯式表格，使多個使用者同時編輯不同段落時不會產生 race condition。每筆段落為獨立資料列，可針對單段進行 row-level 更新。

**Optimistic Locking 流程：**
- 前端 GET 段落時，回應包含 `version` 欄位
- PUT 更新時，必須附上前次取得的 `version`：
  ```
  PUT /api/v1/finetune/correction/:session_id/:segment_id
  Body: {"corrected_text": "...", "expected_version": 3}
  ```
- 後端執行 `UPDATE ... SET version = version + 1 WHERE id = :id AND version = :expected_version`
- 影響列數為 0 → 回 HTTP 409 Conflict（`CORRECTION_VERSION_MISMATCH`），附當前 `version` 與最新內容供前端 reconcile

### 5.6 hotword_groups（Hotword 群組表）

| 欄位 | 類型 | 說明 |
|------|------|------|
| id | SERIAL PK | 主鍵 |
| api_key_id | INTEGER FK | 關聯 api_keys（資料隔離） |
| group_name | VARCHAR(200) | 群組名稱 |
| description | TEXT | 描述 |
| boost_weight | FLOAT DEFAULT 3.0 | 偏置權重 |
| is_active | BOOLEAN DEFAULT true | 是否啟用 |
| created_at | TIMESTAMP WITH TIME ZONE | 建立時間（UTC 儲存，應用層依使用者時區呈現） |
| updated_at | TIMESTAMP WITH TIME ZONE | 更新時間（UTC） |

### 5.7 hotwords（Hotword 詞彙表）

| 欄位 | 類型 | 說明 |
|------|------|------|
| id | SERIAL PK | 主鍵 |
| api_key_id | INTEGER FK NOT NULL | 關聯 api_keys（資料隔離；與父表 hotword_groups.api_key_id 冗餘，避免 Repository 層手動 JOIN） |
| group_id | INTEGER FK | 關聯 hotword_groups |
| word | VARCHAR(200) | 詞彙 |
| pronunciation_hint | VARCHAR(500) | 發音提示 |
| boost_weight | FLOAT | 單詞偏置權重 |
| created_at | TIMESTAMP WITH TIME ZONE | 建立時間 |

**完整性約束：** `hotwords.api_key_id` 必須與對應 `hotword_groups.api_key_id` 相同，透過 trigger 或 application-level 驗證確保一致性。

### 5.8 youtube_downloads（YouTube 下載記錄表）

| 欄位 | 類型 | 說明 |
|------|------|------|
| id | SERIAL PK | 主鍵 |
| api_key_id | INTEGER FK NOT NULL | 關聯 api_keys（資料隔離） |
| url | VARCHAR(2000) | YouTube URL |
| title | VARCHAR(500) | 影片標題 |
| duration_sec | FLOAT | 影片時長 |
| status | VARCHAR(50) | `downloading` / `downloaded` / `transcribing` / `ready_for_correction` / `error` |
| audio_file_id | INTEGER FK | 關聯 audio_files |
| subtitles | JSONB | 下載的字幕 |
| subtitles_status | VARCHAR(20) | 字幕下載狀態：`downloaded` / `partial` / `not_available` |
| correction_session_id | INTEGER FK | 關聯 correction_sessions |
| created_at | TIMESTAMP WITH TIME ZONE | 建立時間 |
| updated_at | TIMESTAMP WITH TIME ZONE | 更新時間 |

### 5.9 api_keys（API 金鑰管理表）

| 欄位 | 類型 | 說明 |
|------|------|------|
| id | SERIAL PK | 主鍵 |
| key_hash | VARCHAR(255) UNIQUE | Argon2id 雜湊值（不儲存明文） |
| name | VARCHAR(200) | 金鑰名稱（用於識別用途） |
| description | TEXT | 用途說明（例如：「客戶 A 質檢系統」） |
| scopes | VARCHAR(50)[] NOT NULL DEFAULT `{'asr:read','asr:write'}` | 權限範圍清單，詳見 19.1.1 節 |
| created_by_key_id | INTEGER FK NULL | 由哪把金鑰建立（追溯用，bootstrap 金鑰為 NULL） |
| rate_limit_override | INTEGER NULL | 個別金鑰限流覆寫（每分鐘請求數，NULL 表示沿用全域 `RATE_LIMIT_PER_MINUTE`） |
| created_at | TIMESTAMP WITH TIME ZONE | 建立時間 |
| expires_at | TIMESTAMP WITH TIME ZONE | 過期時間（null 表示不過期） |
| is_active | BOOLEAN DEFAULT true | 是否啟用 |
| deleted_at | TIMESTAMP WITH TIME ZONE NULL | 軟刪除時間戳；非 NULL 時視為已刪除，但關聯資料保留以維持歷史完整性 |
| last_used_at | TIMESTAMP WITH TIME ZONE | 最後使用時間 |

**索引：**
- `idx_api_keys_key_hash` ON `key_hash`（既有）
- `idx_api_keys_active_not_deleted` ON `(is_active, deleted_at)`（部分索引：`WHERE deleted_at IS NULL`）

**刪除策略：** `DELETE /api/v1/auth/keys/:id` 預設為軟刪除（寫入 `deleted_at`），保留關聯 `transcriptions`、`finetune_tasks` 等資料。徹底刪除（含關聯資料）必須透過 `DELETE /api/v1/auth/keys/:id/erase`（admin scope，符合個資刪除權，詳見 25 節）。

### 5.10 datasets（資料集表）

| 欄位 | 類型 | 說明 |
|------|------|------|
| id | SERIAL PK | 主鍵 |
| api_key_id | INTEGER FK NOT NULL | 關聯 api_keys（資料隔離） |
| name | VARCHAR(200) NOT NULL | 資料集名稱 |
| description | TEXT | 描述 |
| source_type | VARCHAR(30) | 來源：`correction_export` / `jsonl_upload` / `youtube_batch` / `multi_format_conversion` |
| source_session_id | INTEGER FK NULL | 若來自校正工作台匯出，關聯 correction_sessions |
| jsonl_path | VARCHAR(500) | JSONL 檔案儲存路徑 |
| audio_dir | VARCHAR(500) | 音檔目錄路徑 |
| total_duration_sec | FLOAT | 總時長（秒） |
| total_segments | INTEGER | 總段落數 |
| unique_speakers | INTEGER | 唯一語者數 |
| validation_status | VARCHAR(30) | `pending` / `valid` / `invalid` |
| validation_errors | JSONB | 驗證錯誤清單 |
| quality_score | FLOAT | 品質評分（0-100，依 17 節評估） |
| quality_breakdown | JSONB | 各維度子分數 |
| version | INTEGER NOT NULL DEFAULT 1 | 版本號（支援同名資料集的歷次匯出） |
| is_active | BOOLEAN DEFAULT true | 是否可供新訓練任務使用 |
| created_at | TIMESTAMP WITH TIME ZONE | 建立時間（UTC 儲存，應用層依使用者時區呈現） |
| updated_at | TIMESTAMP WITH TIME ZONE | 更新時間（UTC） |

**設計理由：** 將資料集從 `finetune_tasks.dataset_path` 字串欄位提升為一級實體，使下列場景成為可能：
- 同一資料集供多個訓練任務重複使用
- 資料集版本追溯（校正工作台匯出 v1 → v2 → v3）
- 資料集獨立的品質評估與標籤管理

**`finetune_tasks` 表須調整：** 移除 `dataset_path`、`dataset_quality_score`，改為 `dataset_id INTEGER FK NOT NULL`（指向 datasets.id）。

### 5.11 finetune_checkpoints（訓練檢查點表）

| 欄位 | 類型 | 說明 |
|------|------|------|
| id | SERIAL PK | 主鍵 |
| api_key_id | INTEGER FK NOT NULL | 關聯 api_keys（資料隔離） |
| task_id | INTEGER FK NOT NULL | 關聯 finetune_tasks |
| checkpoint_step | INTEGER NOT NULL | 訓練步數 |
| checkpoint_epoch | INTEGER NOT NULL | 訓練 epoch |
| storage_path | VARCHAR(500) | 檔案路徑 |
| size_bytes | BIGINT | 檔案大小（位元組） |
| train_loss | FLOAT | 訓練 loss |
| val_loss | FLOAT | 驗證 loss |
| val_wer | FLOAT | 驗證集 WER |
| is_best | BOOLEAN DEFAULT false | 是否為最佳 checkpoint |
| is_loaded | BOOLEAN DEFAULT false | 是否為當前推理使用的 checkpoint |
| backup_status | VARCHAR(30) | `local` / `backed_up` / `archive_only`（local 已刪除，僅留異地備份） |
| backup_path | VARCHAR(500) NULL | 異地備份路徑（rclone target） |
| auto_cleanup_at | TIMESTAMP WITH TIME ZONE NULL | 預定自動清理時間（保留策略） |
| created_at | TIMESTAMP WITH TIME ZONE | 建立時間（UTC 儲存，應用層依使用者時區呈現） |

**索引：** `UNIQUE (task_id, checkpoint_step)`

**Checkpoint 保留策略：**
- 預設保留每個任務的 `is_best = true` checkpoint 永久（依客戶要求可調整）
- 非最佳 checkpoint 保留 `FINETUNE_SAVE_LIMIT`（預設 5）個，較舊的自動刪除
- 訓練完成 30 天後，非最佳 checkpoint 全部刪除實體檔案，但保留 metadata（`backup_status = 'archive_only'`）
- 已備份至異地的 checkpoint 可隨時還原（透過 `POST /api/v1/finetune/checkpoints/:id/restore`）

---

## 六、資料流設計

### 6.1 離線辨識流程
```
使用者拖拉上傳音檔 → AudioUploader 組件
  → 前端調用 POST /api/v1/asr/transcribe
  → Backend 處理佇列入列：
    1. 音檔儲存到 /data/audio/
    2. 音檔預處理：
       a. 偵測原始取樣率
       b. 重取樣至 16kHz（Kaiser windowed sinc / soxr VHQ）
       c. 轉 mono WAV
    3. 【可選降噪】ClearVoice 降噪 → 淨化音檔
    4. 【VAD】FireRedVAD 語音活動檢測 → 過濾靜音區段
    5. 【ASR 推理】Qwen3-ASR-1.7B → 文字 + 語言
    6. 【對齊】Forced Aligner → 時間戳
    7. 【可選】pyannote 語者分離
    8. 【後處理】文字後處理管道：
       a. 【可選】NEC 命名實體糾錯
       b. 【可選】標點預測
       c. 【可選】KenLM 語言模型重新評分
       d. 簡繁轉換、特殊字元移除、全形轉半形、數字轉換、文字正規化
       e. 【可選】同音異字糾錯
       f. 【可選】LLM 語境校正建議
    9. 寫入 PostgreSQL transcriptions 表
  → 回傳 JSON 結果
  → Frontend 渲染 TranscriptViewer + TimelineViewer + SpeakerSegments
```

### 6.2 質檢 WebSocket 流程
```
外部質檢系統 → WebSocket 連線 ws://host:8000/ws/quality
  → 發送 JSON 封包（含 base64 音檔 + 參數）
  → Backend Worker Thread 接收，加入處理佇列
  → 異步執行 ASR 管線（同 6.1 流程）
  → 寫入 PostgreSQL（source = 'quality_ws'）
  → 透過 WebSocket 回傳 JSON 結果
```

### 6.3 Fine-tune 流程
```
前端上傳 JSONL + 音檔 → POST /api/v1/finetune/upload
  → 儲存到 /data/audio/finetune/
  → POST /api/v1/finetune/validate → 驗證資料格式
  → POST /api/v1/finetune/datasets/:id/evaluate → 資料集品質評估
  → 前端建立訓練任務 → POST /api/v1/finetune/tasks
  → Backend 啟動獨立 Process 執行 torchrun 訓練
  → 訓練 Process 定時將 loss 寫入資料庫
  → 前端訂閱 SSE 事件串流（EventSource）GET /api/v1/events
  → 訓練進度變更時主動推送 finetune:progress 事件（替代輪詢）
  → LossChart 組件即時更新（含驗證 WER 曲線）
  → 輪詢作為降級方案保留（SSE 斷線時自動切換回 GET /api/v1/finetune/tasks/:id）
  → 早停機制自動停止（patience=3）
  → 訓練完成，可用 POST /api/v1/finetune/tasks/:id/load 載入
```

### 6.4 YouTube 下載 → Dataset 建立流程
```
使用者輸入 YouTube URL → YouTubeDownloader 組件
  → 前端訂閱 SSE 事件串流（EventSource）GET /api/v1/events
  → POST /api/v1/dataset/youtube/download
  → yt-dlp 下載音檔 + 字幕
  → SSE 推送 youtube:download:progress 事件（即時更新下載進度）
  → 自動重取樣至 16kHz mono WAV
  → SSE 推送 youtube:download:complete 事件（下載完成通知）
  → POST /api/v1/dataset/youtube/:id/transcribe
  → ASR 自動轉錄 + 字幕作為初始參考
  → 進入校正工作台（correction_session 建立）
  → 使用者逐句校正
  → 匯出 JSONL → 資料集品質評估 → Fine-tune
```

---

## 七、Docker 部署配置

### 7.1 docker-compose.yml 核心配置

```yaml
services:
  postgres:
    build:
      context: ./postgres
      dockerfile: Dockerfile
    # 自訂映像：postgres:16-alpine + zhparser 擴充（詳見 11.2 節）
    environment:
      POSTGRES_DB: asr_platform
      POSTGRES_USER: asr_user
      POSTGRES_PASSWORD: ${DB_PASSWORD}
      POSTGRES_INITDB_ARGS: "--encoding=UTF-8 --locale=C"
      TZ: Asia/Taipei
    volumes:
      - pg-data:/var/lib/postgresql/data
    restart: unless-stopped
    networks:
      - backend
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U asr_user -d asr_platform"]
      interval: 5s
      timeout: 3s
      retries: 10
      start_period: 10s
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "5"

  asr-backend:
    build:
      context: ./backend
      dockerfile: docker/Dockerfile
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql://asr_user:${DB_PASSWORD}@postgres:5432/asr_platform?sslmode=${DB_SSLMODE:-require}
      ASR_MODEL: Qwen/Qwen3-ASR-1.7B
      ALIGNER_MODEL: Qwen/Qwen3-ForcedAligner-0.6B
      BACKEND_TYPE: vllm
      VLLM_GPU_MEMORY_UTILIZATION: ${VLLM_GPU_MEMORY_UTILIZATION:-0.8}
      GPU_DEVICE: cuda:0
      TZ: Asia/Taipei
    volumes:
      - ./data/audio:/data/audio
      - ./data/models:/data/models
      - ./data/checkpoints:/data/checkpoints
      - ./data/noise-dataset:/data/noise-dataset
    restart: unless-stopped
    networks:
      - frontend
      - backend
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    depends_on:
      postgres:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 15s
      timeout: 5s
      retries: 3
      start_period: 60s
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "5"

  asr-frontend:
    build:
      context: ./frontend
      dockerfile: docker/Dockerfile
    ports:
      - "3000:3000"
    environment:
      NEXT_PUBLIC_API_URL: http://asr-backend:8000
      NEXT_PUBLIC_WS_URL: ws://asr-backend:8000
      TZ: Asia/Taipei
    restart: unless-stopped
    networks:
      - frontend
    depends_on:
      asr-backend:
        condition: service_healthy
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "5"

volumes:
  pg-data:

networks:
  frontend:
    driver: bridge
  backend:
    driver: bridge
    internal: true
```

### 7.2 Backend Dockerfile 要點

**三階段建構：**

**Stage 1（builder）：** `nvidia/cuda:12.4.1-devel-ubuntu22.04`
- 安裝 build-essential、python3.12-dev、gcc、g++
- 編譯 FlashAttention 2、kenlm（需完整編譯工具鍊）
- 此階段產物僅用於 Stage 2，不進入最終映像

**Stage 2（deps）：** `nvidia/cuda:12.4.1-runtime-ubuntu22.04`
- 安裝 Python 3.12 與系統依賴（curl、libpq-dev、libmagic1 等）
- pip install 所有 Python 依賴套件（qwen-asr、pyannote.audio、opencc、fireredasr2s、ClearerVoice-Studio、yt-dlp、torchaudio、audiomentations、jieba、cn2an、bitsandbytes、python-magic、slowapi、opentelemetry-instrumentation-fastapi、prometheus-client、FastAPI、uvicorn 等）
- 從 builder 階段複製 FlashAttention 2、kenlm 編譯產物
- **必載模型下載：** 透過 `huggingface-cli download` 在 deps 階段下載 ASR + Aligner + VAD 模型權重至 `/data/models`
- **模型權重完整性驗證：** 下載完成後執行 SHA256 比對，失敗則建構中止：
  ```bash
  sha256sum -c /tmp/model-checksums.txt
  # model-checksums.txt 範例：
  # <expected_sha256>  /data/models/Qwen3-ASR-1.7B/model.safetensors
  # <expected_sha256>  /data/models/Qwen3-ForcedAligner-0.6B/model.safetensors
  # <expected_sha256>  /data/models/FireRedVAD/model.bin
  ```
  - 預期 SHA256 由規格維護者每次模型版本升級時更新至 `backend/docker/model-checksums.txt`
  - 防範供應鏈攻擊：若 HuggingFace 遭入侵或 DNS 劫持，植入的權重會因雜湊不符被攔截
- 下載 OpenSLR RIRS_NOISES 噪音資料庫至 `/data/noise-dataset`，並驗證 archive SHA256

**Stage 3（runtime）：** `nvidia/cuda:12.4.1-runtime-ubuntu22.04`
- 複製 deps 階段所有產物（Python 環境 + 模型權重 + 噪音資料庫）
- 複製應用程式碼
- 建立非 root 使用者（appuser, UID 1000）
- 暴露 8000（HTTP API + WebSocket，單端口方案）
- entrypoint.sh 流程：Alembic 遷移 → 按需模型下載（pyannote、ClearVoice、NEC）→ 權限修正 → Uvicorn 啟動
- Entry point 啟動 Uvicorn（workers=1，因 WebSocket + HTTP 共用端口）
- 多 worker 模式下 WebSocket 連線會綁定到特定 worker，導致連線管理複雜
- 如需水平擴展，V2 升級為 Redis + 多個獨立 Worker 實例

**模型權重打包策略：**
- 開發環境：bind mount `./data/models`，首次啟動自動下載（`huggingface_hub.snapshot_download`）
- 生產環境：Dockerfile deps 階段透過 `huggingface-cli download` 嵌入映像
- 必載模型（ASR + Aligner + VAD）在 deps 階段下載
- 按需模型（pyannote、ClearVoice、NEC）首次啟用時下載
- 需要 `HF_TOKEN` 環境變數時支援受權模型

### 7.3 Frontend Dockerfile 要點

**兩階段建構：**

**Stage 1（builder）：** `node:20-alpine`
- 安裝依賴套件（npm ci）
- 執行 `next build` 編譯產出 `.next/` 目錄

**Stage 2（runtime）：** `node:20-alpine`
- 僅複製 `.next/`、`node_modules/`、`package.json`、`next.config.ts`
- 採用 standalone output 模式（`output: 'standalone'`），僅包含 Next.js 運行時必要檔案
- 複製 `public/` 靜態資源
- 建立非 root 使用者（nodeuser, UID 1001）
- 暴露 3000

### 7.4 NVIDIA Container Toolkit 配置

**部署前置條件：** Host 必須安裝 NVIDIA Container Toolkit，否則 GPU 無法掛載到容器。

**安裝步驟（Ubuntu）：**
1. 新增 NVIDIA GPG key 與 repository
2. 安裝 `nvidia-container-toolkit`
3. 執行 `nvidia-ctk runtime configure --runtime=docker`
4. 重啟 Docker daemon

**驗證：** `docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi`

**開發環境注意：** Windows + Docker Desktop 的 NVIDIA GPU 支援有限（僅 WSL2 部分支援）。
後端 GPU 服務建議在 Linux 環境運行；Windows 開發環境僅用於前端開發與資料庫。

---

## 八、錯誤處理設計

| 情境 | 處理方式 | 錯誤碼 |
|------|---------|--------|
| GPU OOM | 自動降低 batch size 重試（最多 3 次），仍失敗則回 503 | `ASR_GPU_OOM` |
| GPU driver 崩潰 / 裝置不可見 | `/readiness` 回 503；新請求拒絕；既有 WS 斷線；30 秒重試（詳見 18.1.1） | `GPU_UNAVAILABLE` |
| GPU 過熱 > 85°C | 暫停接收新任務直至降溫 | `GPU_UNAVAILABLE` |
| 音檔格式不支援 | 回傳 HTTP 400 + 支援格式列表 | `UPLOAD_AUDIO_FORMAT_UNSUPPORTED` |
| 音檔 MIME 偽造 | python-magic 偵測拒絕；HTTP 400 | `UPLOAD_MIME_NOT_ALLOWED` |
| 音檔時長超過 20 分鐘 | ASR 階段切段（每段 ≤ 20 分鐘）；ForcedAligner 階段切段（每段 ≤ 5 分鐘） | - |
| 音檔大量湧入 | 進入佇列排隊；超過上限回 503 | `QUEUE_FULL` |
| 模型載入失敗 | 依 18.3 fallback 決策表處理；無 fallback 時回 500 | `MODEL_LOAD_FAILED` |
| ASR 主模型失敗 | 自動 fallback 至 0.6B 備援模型 | `MODEL_FALLBACK_ENGAGED`（warning） |
| Aligner 失敗 | fallback 至 VAD 切點 | `MODEL_FALLBACK_ENGAGED`（warning） |
| pyannote 失敗 | fallback 至 CAM++（CPU） | `MODEL_FALLBACK_ENGAGED`（warning） |
| Fine-tune 訓練中斷 | 保留 checkpoint，支援 resume；子行程 PID 記錄於 `process_pid` 欄位 | `FINETUNE_RESUME_FAILED` |
| Fine-tune VRAM 不足 | 拒絕啟動，回傳當前可用 VRAM 與需求 | `FINETUNE_VRAM_INSUFFICIENT` |
| Fine-tune 已有任務在跑 | 拒絕新建（V1 限制 1 個並行） | `FINETUNE_CONCURRENT_LIMIT` |
| WS 質檢端斷線 | 客戶端自動重連（指數退避）；Backend 維持 connection pool | - |
| WS 認證失敗 | 立即關閉連線（close code 1008） | `AUTH_WS_PROTOCOL_INVALID` |
| 資料庫連線失敗 | FastAPI 健康檢查返回 HTTP 503 | `SYSTEM_DATABASE_UNAVAILABLE` |
| 訓練同時進行推理 | 自動降低推理 batch size = 1 避免 OOM；pyannote 降級為 CAM++ | - |
| Fine-tune 資料格式錯誤 | 驗證階段即拒絕，回傳詳細錯誤清單 | `FINETUNE_DATASET_INVALID` |
| VAD 處理失敗 | fallback 至能量閾值法；不回傳錯誤 | `MODEL_FALLBACK_ENGAGED`（warning） |
| YouTube 下載失敗 | 記錄錯誤狀態，支援重試 | `DATASET_YOUTUBE_DOWNLOAD_FAILED` |
| YouTube 字幕下載失敗 | 音檔成功但字幕失敗時，`subtitles_status` 設為 `not_available`，自動觸發 ASR 產出初始文字作為校正參考，前端顯示警示 | `DATASET_YOUTUBE_SUBTITLES_UNAVAILABLE`（warning） |
| YouTube 字幕部分下載 | 僅取得部分語言字幕時，`subtitles_status` 設為 `partial`，以可用字幕作為校正參考 | - |
| 重取樣失敗 | 回傳錯誤，列出原始取樣率與支援範圍 | `UPLOAD_SAMPLE_RATE_OUT_OF_RANGE` |
| 校正並發衝突 | 409 + 當前版本與最新內容 | `CORRECTION_VERSION_MISMATCH` |
| 冪等性鍵 payload 不符 | 422 拒絕 | `IDEMPOTENCY_KEY_PAYLOAD_MISMATCH` |
| 上傳分片完整性失敗 | 拒絕該片，要求重傳 | `UPLOAD_CHUNK_HASH_MISMATCH` |
| 磁碟空間不足 | 拒絕新請求；停止 fine-tune 訓練 | `STORAGE_DISK_FULL` |

---

## 九、擴展功能建議

### 高優先級（V2 優先考量）
1. **實時串流辨識** — Qwen3-ASR 已原生支援 streaming/offline 統一推理
2. **批量辨識佇列升級** — 將記憶體佇列升級為 Redis 佇列
3. **情感分析** — 整合 SenseVoice，偵測情緒標籤
4. **多模型路由** — 依偵測語言自動切換最佳模型
5. **OpenAI 相容 API** — 提供 `/v1/audio/transcriptions` 端點

### 中優先級
6. **聲紋辨識** — 說話者身份確認（wespeaker）
7. **翻譯功能** — 結合 Qwen3-Omni 多語言能力
8. **RBAC 權限管理** — 多使用者、角色權限控制
9. **音訊超解析** — NovaSR 模型提升低品質音檔音質

---

## 十、環境變數配置

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `API_KEY` | - | API 認證金鑰（必填，系統啟動時自動建立為預設金鑰） |
| `API_KEY_ROTATION_DAYS` | `90` | 建議金鑰輪換週期（天） |
| `API_KEY_MAX_COUNT` | `10` | 最大金鑰數量 |
| `ASR_MODEL` | `Qwen/Qwen3-ASR-1.7B` | 預設 ASR 模型 |
| `ALIGNER_MODEL` | `Qwen/Qwen3-ForcedAligner-0.6B` | 對齊模型 |
| `BACKEND_TYPE` | `vllm` | 強制指定為 vLLM 推理後端 |
| `VLLM_GPU_MEMORY_UTILIZATION` | `0.8` | vLLM 預留給非 ASR 模型 (如 VAD/分離) 的 VRAM 比例配置 |
| `GPU_DEVICE` | `cuda:0` | GPU 裝置 |
| `MAX_INFERENCE_BATCH` | `32` | 推理批次上限 |
| `DIARIZATION_ENABLED` | `true` | 啟用語者分離 |
| `POST_PROCESSING_ENABLED` | `true` | 啟用文字後處理 |
| `VAD_ENABLED` | `true` | 啟用 VAD（建議常開） |
| `DENOISE_ENABLED` | `false` | 啟用 ClearVoice 降噪 |
| `NEC_ENABLED` | `false` | 啟用 NEC 命名實體糾錯 |
| `PUNCTUATION_ENABLED` | `false` | 啟用標點預測 |
| `DATABASE_URL` | - | PostgreSQL 連線字串 |
| `DB_PASSWORD` | - | 資料庫密碼 |
| `MODEL_CACHE_DIR` | `/data/models` | 模型快取路徑 |
| `AUDIO_STORAGE_DIR` | `/data/audio` | 音檔儲存路徑 |
| `CHECKPOINT_DIR` | `/data/checkpoints` | Checkpoint 儲存路徑 |
| `FINETUNE_MAX_CONCURRENT` | `1` | 最大並行訓練數 |
| `FINETUNE_SAVE_LIMIT` | `5` | 保留 checkpoint 數量 |
| `MAX_QUEUE_SIZE` | `100` | 處理佇列最大容量 |
| `SUPPORTED_AUDIO_FORMATS` | `wav,mp3,mp4,flac,aac,ogg,m4a` | 支援的音檔格式 |
| `MAX_UPLOAD_SIZE_MB` | `500` | 單檔上傳上限 |
| `RATE_LIMIT_PER_MINUTE` | `30` | 每分鐘請求上限 |
| `WS_MAX_MESSAGE_SIZE_MB` | `50` | WS 單條訊息上限 |
| `CORS_ORIGINS` | `http://localhost:3000` | 允許的前端來源 |
| `AUDIO_RETENTION_DAYS` | `30` | 音檔保留天數（0 = 永久） |
| `DISK_CLEANUP_SCHEDULE` | `0 3 * * *` | 定時清理排程 |
| `DATA_AUGMENTATION_ENABLED` | `false` | 啟用資料增強 |
| `AUGMENT_NOISE_DIR` | `/data/noise-dataset` | 噪音資料庫路徑 |
| `AUGMENT_PITCH_SHIFT_SEMITONES` | `4` | 音高偏移範圍（半音） |
| `AUGMENT_TIME_STRETCH_RANGE` | `0.8,1.25` | 時間拉伸範圍 |
| `CORRECTION_KENLM_ENABLED` | `false` | 啟用 KenLM 糾錯 |
| `CORRECTION_KENLM_MODEL` | `/data/models/kenlm.arpa` | KenLM 模型路徑 |
| `CORRECTION_HOMOPHONE_ENABLED` | `false` | 啟用同音異字糾錯 |
| `CORRECTION_LLM_ENABLED` | `false` | 啟用 LLM 輔助糾錯 |
| `CORRECTION_LLM_MODEL` | `Qwen/Qwen2.5-7B` | LLM 糾錯模型 |
| `CORRECTION_LLM_QUANTIZATION` | `int4` | LLM 糾錯量化等級（`int4` / `int8` / `none`） |
| `ENCRYPTION_KEY` | - | 音檔加密金鑰（可選，64 字元 hex 字串，啟用時對音檔 AES-256-GCM 加密） |
| `DB_SSLMODE` | `require` | PostgreSQL TLS 連線模式 |
| **佇列雙通道** | | |
| `QUEUE_REALTIME_MAX_SIZE` | `50` | realtime 通道（WS）佇列上限 |
| `QUEUE_BATCH_MAX_SIZE` | `20` | batch 通道（離線）佇列上限 |
| `QUEUE_REJECT_BEHAVIOR` | `reject` | 佇列滿載行為：`reject` / `wait` |
| **分片上傳** | | |
| `CHUNKED_UPLOAD_THRESHOLD_MB` | `100` | 超過此值必須使用分片上傳 |
| `CHUNKED_UPLOAD_TTL_HOURS` | `24` | 未完成上傳的清理時間 |
| **限流與安全** | | |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | 滑動視窗大小 |
| `WS_MAX_CONNECTIONS_PER_KEY` | `10` | 單金鑰最大同時 WS 連線數 |
| `CORS_ALLOW_CREDENTIALS` | `false` | 是否允許跨域帶 cookie |
| `OPENAPI_DOCS_ENABLED` | `true` | 是否啟用 OpenAPI 文檔端點 |
| `OPENAPI_DOCS_REQUIRE_AUTH` | `false` | OpenAPI 文檔是否要求認證（prod 強制 `true`） |
| **冪等性** | | |
| `IDEMPOTENCY_TTL_HOURS` | `24` | Idempotency-Key 儲存時間 |
| **GPU 故障處理** | | |
| `GPU_TEMP_THRESHOLD_C` | `85` | GPU 過熱閾值（攝氏） |
| `ALLOW_CPU_FALLBACK` | `false` | GPU 完全不可用時是否 fallback 至 CPU 推理 |
| **可觀測性** | | |
| `LOG_LEVEL` | `INFO` | 日誌等級 |
| `LOG_FORMAT` | `json` | 日誌格式（`json` / `text`） |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | - | OpenTelemetry OTLP endpoint |
| `OTEL_SERVICE_NAME` | `asr-backend` | OpenTelemetry 服務名稱 |
| `OTEL_TRACES_SAMPLER_ARG` | `0.1` | tracing 取樣率 |
| `METRICS_ENABLED` | `true` | 是否啟用 `/metrics` 端點 |
| **SLO/SLA** | | |
| `SLO_ALERT_WEBHOOK_URL` | - | 違規通知 Webhook |
| `SLO_AVAILABILITY_TARGET` | `0.995` | 可用率目標 |
| **災難復原** | | |
| `PG_BACKUP_SCHEDULE` | `0 2 * * *` | PostgreSQL 備份排程 |
| `PG_BACKUP_TARGET` | `/backup/postgres` | 備份儲存路徑 |
| `PG_BACKUP_RETENTION_DAYS` | `30` | 備份保留天數 |
| `CHECKPOINT_BACKUP_TARGET` | - | Checkpoint 異地備份 rclone target |
| `AUDIO_BACKUP_ENABLED` | `false` | 是否啟用音檔備份 |
| `AUDIO_BACKUP_TARGET` | - | 音檔備份 rclone target |
| **個資合規** | | |
| `AUDIT_LOG_RETENTION_DAYS` | `730` | 審計日誌保留天數 |
| `DATA_EXPORT_URL_TTL_HOURS` | `24` | 個資匯出下載連結有效期 |
| `ERASE_CONFIRMATION_REQUIRED` | `true` | 個資刪除是否要求三次確認 |
| **第三方授權** | | |
| `THIRD_PARTY_LICENSE_ACK` | `false` | 是否已接受第三方授權，未設定則拒絕啟動 |
| **環境識別** | | |
| `ENV` | `development` | 部署環境（`development` / `staging` / `production`） |
| `DEPLOYMENT_PROFILE` | `client` | 部署 profile（`client` / `vendor`） |
| `HF_TOKEN` | - | HuggingFace 受權模型下載 token（pyannote 必需） |

---

## 十一、資料庫索引與全文檢索

### 11.1 索引清單

```sql
CREATE INDEX idx_transcriptions_status ON transcriptions(status);
CREATE INDEX idx_transcriptions_created_at ON transcriptions(created_at DESC);
CREATE INDEX idx_transcriptions_source ON transcriptions(source);
CREATE INDEX idx_transcriptions_api_key_id ON transcriptions(api_key_id);
CREATE INDEX idx_finetune_tasks_status ON finetune_tasks(status);
CREATE INDEX idx_finetune_tasks_api_key_id ON finetune_tasks(api_key_id);
CREATE INDEX idx_audio_files_transcription_id ON audio_files(transcription_id);
CREATE INDEX idx_audio_files_api_key_id ON audio_files(api_key_id);
CREATE INDEX idx_correction_sessions_session_id ON correction_sessions(session_id);
CREATE INDEX idx_correction_sessions_status ON correction_sessions(status);
CREATE INDEX idx_correction_sessions_api_key_id ON correction_sessions(api_key_id);
CREATE INDEX idx_hotwords_group_id ON hotwords(group_id);
CREATE INDEX idx_hotwords_api_key_id ON hotwords(api_key_id);
CREATE INDEX idx_hotword_groups_is_active ON hotword_groups(is_active);
CREATE INDEX idx_hotword_groups_api_key_id ON hotword_groups(api_key_id);
CREATE INDEX idx_youtube_downloads_status ON youtube_downloads(status);
CREATE INDEX idx_youtube_downloads_api_key_id ON youtube_downloads(api_key_id);
CREATE INDEX idx_api_keys_key_hash ON api_keys(key_hash);
CREATE INDEX idx_api_keys_active_not_deleted ON api_keys(is_active) WHERE deleted_at IS NULL;
CREATE INDEX idx_correction_segments_session_id ON correction_segments(session_id);
CREATE INDEX idx_correction_segments_is_modified ON correction_segments(is_modified);
CREATE INDEX idx_correction_segments_api_key_id ON correction_segments(api_key_id);
CREATE INDEX idx_datasets_api_key_id ON datasets(api_key_id);
CREATE INDEX idx_finetune_checkpoints_task_id ON finetune_checkpoints(task_id);
CREATE INDEX idx_audit_logs_api_key_id_created ON audit_logs(api_key_id, created_at DESC);
CREATE INDEX idx_audit_logs_event_type ON audit_logs(event_type);
```

### 11.2 中文全文檢索（zhparser 擴充）

**問題背景：** PostgreSQL 原生不支援中文分詞，預設 `to_tsvector('chinese', ...)` 會失敗。必須安裝 `zhparser` 擴充（基於 SCWS 分詞器，PG 16 相容）。

**初始化步驟（容器啟動時由 Alembic migration 執行）：**

```sql
-- 1. 安裝擴充（需在 postgres 映像中預先編譯）
CREATE EXTENSION IF NOT EXISTS zhparser;

-- 2. 建立 text search configuration
CREATE TEXT SEARCH CONFIGURATION chinese (PARSER = zhparser);

-- 3. 設定分詞輸出（n=名詞、v=動詞、a=形容詞、i=成語、l=習慣用語、t=時間詞、x=外文）
ALTER TEXT SEARCH CONFIGURATION chinese
  ADD MAPPING FOR n,v,a,i,l,t,x WITH simple;

-- 4. 建立全文檢索索引
CREATE INDEX idx_transcriptions_text_gin
  ON transcriptions USING gin(to_tsvector('chinese', transcript_text));
CREATE INDEX idx_transcriptions_normalized_text_gin
  ON transcriptions USING gin(to_tsvector('chinese', normalized_text));
CREATE INDEX idx_correction_segments_text_gin
  ON correction_segments USING gin(to_tsvector('chinese', corrected_text));
```

**postgres 映像建構（7.1 節 docker-compose 已調整為支援 zhparser 的自訂映像）：**

```dockerfile
# postgres/Dockerfile
FROM postgres:16-alpine
RUN apk add --no-cache build-base postgresql-dev git \
 && git clone --depth 1 https://github.com/amutu/zhparser.git /tmp/zhparser \
 && cd /tmp/zhparser \
 && make && make install \
 && apk del build-base postgresql-dev git \
 && rm -rf /tmp/zhparser
```

**查詢範例：**
```sql
-- 搜尋包含「中央銀行」的逐字稿
SELECT id, file_name, transcript_text
FROM transcriptions
WHERE to_tsvector('chinese', transcript_text) @@ plainto_tsquery('chinese', '中央銀行')
  AND api_key_id = :current_key_id
ORDER BY created_at DESC;
```

**繁簡相容：** zhparser 的字典基於簡體，繁體輸入需先透過 OpenCC 轉換為簡體後再執行 `to_tsvector`。建議在應用層統一處理（查詢時將 keyword 簡化）。

---

## 十二、音檔取樣率自适应處理

### 12.1 問題背景

客戶音檔取樣率介於 8kHz 到 48kHz 之間，無法硬性控制來源。若 8kHz 音檔直接餵給預期 16kHz 的模型，準確率會從 98% 降至 60%。

### 12.2 取樣率偵測與自動重取樣策略

| 原始取樣率 | 處理方式 | 重取樣方法 | 預期效果 |
|------------|---------|-----------|---------|
| 8kHz | 上採樣至 16kHz | `torchaudio.transforms.Resample`（Kaiser windowed sinc）或 `soxr`（VHQ） | WER 改善 4-7% |
| 16kHz | 無需處理 | - | 基準準確率 |
| 44.1kHz / 48kHz | 下採樣至 16kHz | 保留 6-8kHz 範圍摩擦音 | 減少不必要運算 |

**流程：**
```
音檔上傳 → 偵測原始取樣率與位元深度 → 判斷是否需要重取樣
  → 【安全隔離】解析與轉碼操作必須位於獨立的 try-except 區塊，並加上處理超時 (Timeout) 限制，防範惡意偽造音檔造成的 C++ Segmentation Fault 拖垮主行程
  → 若為 8-bit → 強制轉換為 16-bit PCM / float32（避免精度異常）
  → 8kHz → Kaiser windowed sinc 上採樣 → 16kHz mono WAV
  → 16kHz → 直接通過
  → 44.1kHz/48kHz → 下採樣（保留摩擦音）→ 16kHz mono WAV
  → 【可選】ClearVoice 降噪 → FireRedVAD → ASR 管線
```

### 12.3 重取樣程式碼範例

```python
import torchaudio

def resample_audio(input_path: str, output_path: str, target_sr: int = 16000) -> int:
    """偵測原始取樣率並重取樣至目標取樣率。"""
    waveform, orig_sr = torchaudio.load(input_path)

    # 轉 mono
    if waveform.shape[0] > 1:
        waveform = waveform.mean(dim=0, keepdim=True)

    if orig_sr != target_sr:
        resampler = torchaudio.transforms.Resample(
            orig_freq=orig_sr,
            new_freq=target_sr,
            low_pass_filter_width=64,
            rolloff=0.9475937167092650
        )
        waveform = resampler(waveform)

    import soundfile as sf
    sf.write(output_path, waveform.squeeze().numpy(), target_sr, subtype='PCM_16')
    return orig_sr
```

---

## 十三、Hotword / 自訂詞彙功能

### 13.1 問題背景

個別客戶環境有專有名詞（產品名稱、技術術語、人名），需要 hotword biasing 提升辨識準確率。

### 13.2 Hotword 應用策略（三層架構）

| 層級 | 適用規模 | 技術方案 | 訓練需求 | 延遲影響 |
|------|---------|---------|---------|---------|
| 層一（Shallow Fusion） | < 100 詞 | 解碼時給予詞彙表獎勵（decoder bias） | 無需額外訓練 | 無 |
| 層二（CTC Word Spotter） | 100-1000 詞 | 輔助 CTC 編碼器產生逐幀 log-probabilities | 需訓練 CTC-WS 編碼器 | 低 |
| 層三（Fine-tune） | > 1000 詞 | 透過 fine-tune 將詞彙內建到模型 | 需完整 fine-tune | 無（已內建） |

**流程：**
```
使用者建立 hotword 群組 → 新增詞彙 → 啟用群組
  → 系統判斷詞彙數量
    → < 100 詞 → Shallow Fusion（即時生效）
    → 100-1000 詞 → 觸發 CTC-WS 訓練
    → > 1000 詞 → 建議建立 fine-tune 任務
  → 辨識時自動套用已啟用群組
```

**CTC-WS 訓練細節：**
- **CTC-WS 編碼器模型：** 使用 Qwen3-ASR-1.7B 的 CTC 編碼器層作為輔助編碼器（凍結主模型權重，僅訓練 CTC 輸出層）
- **訓練觸發條件：** 當 hotword 群組詞彙數達到 100 詞且使用者手動點擊「訓練 CTC-WS」按鈕時觸發（不自動觸發，避免佔用 GPU）
- **VRAM 需求：** CTC-WS 訓練僅需 ~2 GB VRAM（僅訓練輸出層，主模型凍結）
- **訓練時間：** 約 5-10 分鐘（依詞彙數量）
- **訓練完成後：** CTC-WS 模型存至 `/data/models/hotword-ctc/group_{id}/`，辨識時自動載入

---

## 十四、YouTube 音檔下載與 Dataset 建立

### 14.1 問題背景

需要 YouTube 音檔下載功能以建立校正 dataset。完整流程：YouTube 下載 → ASR 自動轉錄 → 校正工作台修正 → 匯出 JSONL → Fine-tune。

### 14.2 技術實作

- 使用 `yt-dlp`（Python 套件）進行音檔下載
- 支援單影片、播放清單批量下載
- 同時下載自動生成的字幕（作為初始參考）
- 下載後自動轉為 16kHz mono WAV（含取樣率自适应處理）

### 14.3 SSRF 防護

**背景：** 使用者輸入的 URL 直接傳入 yt-dlp 可能導致 Server-Side Request Forgery 攻擊，讓伺服器任意存取內部網路資源。

**防護措施：**
1. **白名單網域：** 僅允許 `youtube.com`、`youtu.be`、`youtube-nocookie.com`，其餘網域一律拒絕並回傳 HTTP 400
2. **強制 HTTPS 協議：** URL 必須以 `https://` 開頭，`http://` 自動轉為 `https://`，其他協議（`ftp://`、`file://` 等）一律拒絕
3. **禁止內部位址解析：** 使用自訂 downloader 或 URL 驗證函式，在 yt-dlp 實際下載前檢查 URL 解析後的 IP 是否為私有位址（`10.x.x.x`、`172.16-31.x.x`、`192.168.x.x`、`127.x.x.x`、`169.254.x.x`）
4. **設定 `restrictfilenames=True`：** 避免檔名包含路徑穿越字元
5. **定期更新 yt-dlp：** Dockerfile 固定 yt-dlp 版本號，定期更新以修補已知漏洞

### 14.4 下載命令範例

```python
import re
import socket
import ipaddress
import yt_dlp

ALLOWED_DOMAINS = {"youtube.com", "youtu.be", "youtube-nocookie.com"}
YOUTUBE_URL_PATTERN = re.compile(
    r"^https://(?:www\.)?(?:youtube\.com/(?:watch\?v=|embed/|shorts/)|youtu\.be/)[a-zA-Z0-9_-]+$"
)

def validate_youtube_url(url: str) -> str:
    """驗證 YouTube URL，防範 SSRF 攻擊。"""
    # 強制 HTTPS
    if url.startswith("http://"):
        url = url.replace("http://", "https://")
    if not url.startswith("https://"):
        raise ValueError("僅支援 https:// 協議")

    # 網域白名單
    parsed = re.match(r"https://(?:www\.)?([^/]+)", url)
    if not parsed or parsed.group(1) not in ALLOWED_DOMAINS:
        raise ValueError(f"不允許的網域：{parsed.group(1) if parsed else url}")

    # URL 格式驗證
    if not YOUTUBE_URL_PATTERN.match(url):
        raise ValueError("URL 格式不符 YouTube 影片或播放清單格式")

    return url

def download_youtube_audio(url: str, output_dir: str):
    """下載 YouTube 音檔與字幕。"""
    url = validate_youtube_url(url)
    ydl_opts = {
        "format": "ba[abr<50]/worstaudio",
        "outtmpl": f"{output_dir}/%(id)s.%(ext)s",
        "restrictfilenames": True,
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "wav", "preferredquality": "0"}
        ],
        "writels": True,
        "writesubtitles": True,
        "subtitleslangs": ["zh-Hant", "zh-TW", "zh", "en"],
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return info.get("title"), info.get("duration")
```

---

## 十五、Fine-tune 訓練強化

### 15.1 訓練參數建議表

依據 Whisper / Qwen3-ASR 官方 fine-tune 範例與內部基準測試，學習率隨資料量單調遞增（大資料集可承受較大 step size）：

| 資料集大小 | 音訊時數 | 建議 Epochs | 學習率 | Batch Size | 預估 GPU 時數（單張 48 GB） |
|------------|----------|-------------|--------|------------|---------|
| Tiny | < 1 小時 | 8-12 | 1e-5 | 4 | 0.5-1 |
| Small | 1-5 小時 | 5-8 | 2e-5 | 8 | 2-5 |
| Medium | 5-20 小時 | 3-5 | 3e-5 | 16 | 8-20 |
| Large | 20-100 小時 | 2-3 | 5e-5 | 32 | 24-80 |

**設計原則：**
- 資料量小 → 學習率低 + epoch 多，避免過擬合
- 資料量大 → 學習率高 + epoch 少，加速收斂
- 所有規模統一啟用 warm-up（前 10% 步驟）與 cosine decay
- 若驗證 WER 開始上升，依 15.2 節早停機制中止

### 15.2 早停機制（Early Stopping）

- 依據驗證集 WER 停止，而非訓練 loss
- 預設 patience = 3（連續 3 個 epoch 無改善則停止）
- 自動保存最佳 checkpoint（WER 最低時的權重）

### 15.3 資料增強管線

| 技術 | 說明 | 效果 |
|------|------|------|
| 背景噪音注入 | 使用 OpenSLR RIRS_NOISES 資料庫 | 提升抗噪能力 |
| 音高偏移（Pitch Shift） | ±4 半音隨機偏移 | 模擬不同語者音域 |
| 時間拉伸（Time Stretch） | 0.8x-1.25x 隨機拉伸 | 模擬不同語速 |
| 響度正規化（LUFS） | 統一音訊響度 | 減少音量差異影響 |
| 環境模擬（RIR 卷積） | 房間脈衝響應卷積 | 提升泛化能力 |

**噪音資料庫來源：**
- **OpenSLR RIRS_NOISES：** https://www.openslr.org/28/（約 10 GB，含 60 種環境噪音 + 房間脈衝響應）
- Docker 映像建構時自動下載並解壓至 `/data/noise-dataset`
- 首次啟動時若資料夾不存在，自動執行下載腳本（`scripts/download_noise_dataset.sh`）

---

## 十六、文字糾錯管線強化

### 16.1 管線架構（四層）

| 層級 | 技術 | 修正類型 | 延遲 |
|------|------|---------|------|
| 層一（NEC） | Generative-Annotation-NEC | 專業術語、中英夾雜 | 低 |
| 層二（KenLM） | 領域 n-gram 語言模型 | 低概率詞組合、語法錯誤 | 低 |
| 層三（同音異字） | 中文發音規則比對 | 同音異字替換 | 中 |
| 層四（LLM 輔助） | Qwen2.5-7B（bitsandbytes INT4 量化，~4.5 GB VRAM） | 語境級校正建議 | 高 |

### 16.2 糾錯管線程式碼結構

```python
class CorrectionPipeline:
    def __init__(self):
        self.nec = NECModel()
        self.kenlm = KenLMModel()
        self.homophone = HomophoneModel()
        self.llm_corrector = LLMCorrector()

    def correct(self, text: str, layers: list = None) -> str:
        """依序執行各層糾錯。layers 為空則執行全部已啟用的層。"""
        if layers is None or 1 in layers:
            text = self.nec.correct(text)
        if layers is None or 2 in layers:
            text = self.kenlm.rescore(text)
        if layers is None or 3 in layers:
            text = self.homophone.correct(text)
        if layers is None or 4 in layers:
            text = self.llm_corrector.suggest(text)
        return text
```

---

## 十七、資料集品質評估

### 17.1 品質評估維度與權重

| 維度 | 權重 | 評估方式 | 建議基準 |
|------|------|---------|---------|
| 語者多樣性 | 25% | 唯一語者數 / 總時數 | > 50 語者 / 100 小時 |
| 領域平衡 | 20% | 部署領域特定資料佔比 | 10-15% |
| 標註品質 | 20% | 人工覆核比例、一致性評分 | > 80% 覆核率 |
| 噪音與環境 | 15% | 非理想聲學條件資料佔比 | 25-40% |
| 規模 | 10% | 總時數 | 100+ 小時為通用基準 |
| 音檔長度分佈 | 10% | 10-30 秒片段佔比 | > 60% |

### 17.2 評分計算方式

```
總分 = Σ(維度得分 × 權重)

維度得分計算：
- 語者多樣性：min(實際語者數 / 建議基準, 1.0) × 100
- 領域平衡：若佔比在建議範圍內得 100 分，否則依偏離程度遞減
- 標註品質：人工覆核比例直接映射為百分比
- 噪音與環境：若佔比在建議範圍內得 100 分，否則依偏離程度遞減
- 規模：min(實際時數 / 100, 1.0) × 100
- 音檔長度分佈：符合 10-30 秒的片段比例直接映射為百分比
```

### 17.3 前端整合

- 訓練任務建立頁面：上傳資料集後自動觸發品質評估
- 品質評分以儀表板呈現（各維度環形圖 + 總分）
- 改善建議以清單顯示
- 評分低於 50 分時顯示警告

---

## 十八、健康檢查與監控

### 18.1 健康檢查端點
| Method | Path | 說明 | 認證 |
|--------|------|------|------|
| GET | `/health` | 基礎存活檢查（200 = 服務運行中） | 豁免 |
| GET | `/readiness` | 就緒檢查（DB 連線 + GPU 可用 + 模型載入完成） | 豁免 |
| GET | `/api/v1/gpu/status` | VRAM 使用量、溫度、模型載入狀態 | Bearer + `asr:read` |
| GET | `/api/v1/queue/status` | 佇列深度、待處理數量、預估等待時間 | Bearer + `asr:read` |

**`/readiness` 檢查項目：**

| 項目 | 通過條件 | 失敗時行為 |
|------|---------|----------|
| PostgreSQL 連線 | `SELECT 1` 在 2 秒內回覆 | 503 `SYSTEM_DATABASE_UNAVAILABLE` |
| GPU 裝置可見 | `nvidia-smi` 回傳成功且裝置數 > 0 | 503 `GPU_UNAVAILABLE` |
| ASR 模型已載入 | `model_load_status{model="asr"} == 1` | 503 `ASR_MODEL_NOT_LOADED` |
| Aligner 模型已載入 | 同上 | 503 `MODEL_LOAD_FAILED` |
| VAD 模型已載入 | 同上 | 503 `MODEL_LOAD_FAILED` |

### 18.1.1 GPU 故障情境行為

**偵測機制：**
- 健康檢查每 15 秒執行 `nvidia-smi --query-gpu=memory.free,temperature.gpu,utilization.gpu`
- vLLM `AsyncLLMEngine` 推理拋 CUDA error 時觸發 GPU 故障事件
- `torch.cuda.is_available()` 從 true 變 false → 立即標記為故障

**故障分級與行為：**

| 故障類型 | 行為 |
|---------|------|
| GPU 完全不可見（driver 崩潰 / 裝置移除） | `/readiness` 回 503；新請求拒絕；既有 WS 連線發 `{"action":"service_unavailable"}` 後關閉；進行中的推理任務標記為 `failed` |
| GPU 可見但 VRAM 全滿無法分配 | 嘗試 `torch.cuda.empty_cache()` 釋放碎片；3 次仍失敗 → 同上 |
| GPU 溫度過高（> `GPU_TEMP_THRESHOLD_C`，預設 85°C） | 暫停接收新任務；既有任務正常完成；溫度降至閾值 5°C 以下 → 自動恢復 |
| 單次推理 CUDA OOM | 自動降 batch size 重試 3 次（規格 8 節既有規則） |

**自動恢復：**
- 系統每 30 秒重新偵測 GPU 狀態，恢復後自動：
  1. 重新載入必載模型
  2. 執行 dummy inference 預熱
  3. `/readiness` 回 200
- 連續 5 次重試仍失敗（150 秒）→ 觸發 P0 incident 並通知值班人員

**降級至 CPU 推理（最終 fallback）：**
- 環境變數 `ALLOW_CPU_FALLBACK=true` 時啟用
- 載入 Qwen3-ASR-0.6B（純 CPU 可運行），效能降至約 0.3 倍即時率
- 標記 response 中 `processing_mode: "cpu_fallback"`，前端顯示警告

### 18.2 模型載入策略
- **必載模型：** ASR + Aligner + VAD（共 ~6.6 GB）
- **按需載入：** pyannote（啟用 diarization 時）、ClearVoice（啟用降噪時）、NEC（啟用糾錯時）、Qwen2.5-7B INT4（啟用 LLM 糾錯時，~4.5 GB）
- **啟動預熱：** 必載模型啟動後執行一次 dummy inference
- **Fine-tune 載入：** 採用雙模型交替策略（Zero-downtime 切換）
	- GPU 48 GB 有足夠空間同時容納兩個 1.7B 模型（~8 GB 總計）
	- 新 checkpoint 載入到 standby 槽位
	- 載入完成後原子性切換 active 指標（毫秒級）
	- 舊模型卸載，請求零中斷
	- 切換期間所有請求正常處理，無排隊延遲

- **Fine-tune 期間 VRAM 隔離策略：**
	- 推理 batch size 強制降為 1（避免 OOM）
	- 使用 `torch.cuda.memory_allocated()` 即時監控 VRAM 使用量
	- Fine-tune 訓練程序設定 CUDA 記憶體限制：
		* `torch.cuda.set_per_process_memory_fraction(0.65)`（限制使用 65% VRAM，約 31 GB）
		* 保留約 17 GB 給推理服務（ASR 4 GB + Aligner 2 GB + 安全餘量）
	- 若監控發現剩餘 VRAM < 8 GB，暫停 Fine-tune 並等待推理請求完成
	- PyTorch cache allocator 碎片問題對策：
		* 每 10 個 training step 執行一次 `torch.cuda.empty_cache()`
		* 使用 `torch.cuda.memory_snapshot()` 記錄碎片狀況（debug 模式）
- **模型切換版本隔離（`POST /api/v1/asr/switch-model`）：**
	- **雙模型過渡：** 新模型載入後，等待所有進行中的推理任務完成，才 unload 舊模型
	- **任務版本綁定：** 每個推理任務在建立時綁定到當時的模型版本（`model_version`），即使模型切換期間，進行中的任務仍使用原模型完成推理
	- **新請求路由：** 模型切換完成後，新請求自動路由到新模型
	- **舊模型卸載條件：** 舊模型上無進行中任務且 VRAM 使用超過閾值時，才觸發 unload
	- **model_version 欄位：** `transcriptions` 表新增 `model_version` 欄位（VARCHAR(50)），記錄每次辨識所使用的模型版本編號，便於追溯與比對

### 18.3 模型載入失敗 Fallback 決策表

每個模型載入失敗時都應有明確的後續行為，避免單一模型問題導致整個服務不可用：

| 模型 | 失敗影響 | Fallback 策略 |
|------|---------|--------------|
| Qwen3-ASR-1.7B（主 ASR） | 服務無法辨識 | 1. 自動嘗試 Qwen3-ASR-0.6B（記錄 warning）<br>2. 兩者皆失敗 → `/readiness` 回 503；管理員告警 |
| Qwen3-ASR-0.6B（備援） | 主模型仍可用時不影響服務 | 記錄錯誤但不告警；下次需要時重試 |
| Qwen3-ForcedAligner-0.6B | 無法產出時間軸 | 1. 自動 fallback 至 VAD 切點作為粗粒度時間軸（精度降低）<br>2. response 中 `alignment_mode: "vad_fallback"`<br>3. 校正工作台仍可使用，但段落邊界精度下降 |
| FireRedVAD | 無法過濾靜音 | 1. 啟用能量閾值法（短時能量 > 動態閾值視為語音）<br>2. response 中 `vad_mode: "energy_threshold"`<br>3. 推理時長預計增加 30% |
| pyannote.audio | 無法執行語者分離 | 1. 自動 fallback 至 CAM++（純 CPU）<br>2. CAM++ 也失敗 → `diarization_status: "unavailable"`，所有段落標 `UNKNOWN` |
| ClearVoice | 無法降噪 | 跳過降噪步驟，直接送 VAD；`denoise_status: "skipped"` |
| Generative-Annotation-NEC | 無法執行 NEC 糾錯 | 跳過該後處理步驟；其他糾錯層仍執行 |
| Qwen2.5-7B INT4（LLM 糾錯） | 無法執行 LLM 糾錯 | 跳過該後處理步驟；其他糾錯層仍執行 |
| KenLM | 無法 rescoring | 跳過該後處理步驟 |

**Fallback 啟用記錄：**
- 任何 fallback 觸發時，在日誌寫入 `WARNING` 級訊息 + 增加 `model_fallback_total{model, fallback}` 指標
- response body 在 `degradation` 欄位列出本次請求觸發的所有 fallback：
  ```json
  {
    "success": true,
    "data": {
      "...": "...",
      "degradation": [
        {"model": "Qwen3-ASR-1.7B", "fallback_to": "Qwen3-ASR-0.6B", "reason": "VRAM insufficient"},
        {"model": "ClearVoice", "fallback_to": "none", "reason": "load failed"}
      ]
    }
  }
  ```

**永不 fallback 的失敗：**
- Aligner 完全不可用且 VAD 也失敗 → 拒絕辨識，回 503
- 必載三模型皆失敗 → 服務無法啟動

---

## 十九、安全性設計

### 19.1 API 認證

**認證機制：多金鑰 + Scope 權限 + 輪換設計**

所有 API 端點（含 WebSocket）要求 `Authorization: Bearer <api_key>` header（WebSocket 透過 Sec-WebSocket-Protocol 傳遞，詳見 3.3.7 節），透過 `api_keys` 資料表驗證。

**金鑰驗證流程：**
1. 接收請求 → 解析 Bearer token
2. 以 Argon2id 雜湊 token，查詢 `api_keys.key_hash`
3. 比對成功 且 `is_active = true` 且 `deleted_at IS NULL` 且未過期 → 更新 `last_used_at` → 進入 scope 檢查
4. 端點所需 scope 必須完全包含於 `api_keys.scopes` → 通過 → 放行
5. 比對失敗 / 已停用 / 已軟刪除 / 已過期 → HTTP 401（`AUTH_INVALID_KEY`）
6. scope 不足 → HTTP 403（`AUTH_INSUFFICIENT_SCOPE`），錯誤訊息列出所需 scope

### 19.1.1 API Scope 權限體系

每把金鑰持有一組 scopes（字串陣列），端點依下表要求的 scope 過濾：

| Scope | 涵蓋端點 | 用途 |
|-------|---------|------|
| `admin` | 所有端點，含金鑰管理、模型切換、刪除他人資料 | 平台管理員專用，**僅 bootstrap 金鑰與 `created_by_key_id` 為 admin 的金鑰可建立** |
| `asr:read` | `GET /api/v1/asr/history/*`、`GET /api/v1/asr/queue`、`GET /api/v1/asr/models`、SSE `queue:*` 事件 | 查詢辨識結果 |
| `asr:write` | `POST /api/v1/asr/transcribe`、`POST /api/v1/asr/upload/*`、WS `/ws/quality` | 提交辨識任務 |
| `asr:delete` | 刪除歷史記錄、取消佇列任務 | 清理本租戶資料 |
| `finetune:read` | `GET /api/v1/finetune/*`（任務、進度、loss）、SSE `finetune:*` 事件 | 查詢訓練狀態 |
| `finetune:write` | 建立 / 取消 / 恢復訓練、上傳資料、校正工作台、匯出 | 完整 fine-tune 流程 |
| `finetune:load` | `POST /api/v1/finetune/tasks/:id/load`、`POST /api/v1/asr/switch-model` | 切換推理模型（高風險操作） |
| `hotword:read` | `GET /api/v1/hotword/*` | 查詢 hotword 群組 |
| `hotword:write` | 建立 / 修改 / 啟用 hotword 群組與詞彙 | 維護 hotword |
| `dataset:youtube` | `POST /api/v1/dataset/youtube/*` | YouTube 下載功能 |

**Scope 解析規則：**
- 端點程式碼以 FastAPI Dependency 強制宣告所需 scope：`Depends(require_scope("asr:write"))`
- `admin` 隱含所有 scope（superset）
- 缺少 `admin` 又呼叫 `POST /api/v1/auth/keys` → 403，避免普通租戶建立新金鑰
- WebSocket `/ws/quality` 在連線時驗證 `asr:write`，否則 1008（Policy Violation）斷線

**預設 scope 配置：**
- Bootstrap 金鑰（環境變數 `API_KEY`）：`['admin']`
- 一般客戶透過 admin 建立金鑰時：預設 `['asr:read','asr:write']`，可由 admin 加減

**健康檢查端點豁免認證：**
- `GET /health`、`GET /readiness` 免認證（供 Kubernetes / Docker Compose 健康檢查使用）
- 其餘所有端點（含 `/api/v1/gpu/status`、`/api/v1/queue/status`）均須認證

**金鑰管理：**
- 系統啟動時，若 `API_KEY` 環境變數存在且 `api_keys` 表為空，自動建立為預設金鑰（backward compatible）
- 支援多金鑰並行（不同服務/使用者使用不同金鑰）
- 金鑰建立時僅顯示一次明文字串，之後僅顯示名稱與最後使用時間
- 金鑰儲存使用 Argon2id 雜湊（time_cost=3, memory_cost=65536, parallelism=4）
- 支援設定過期時間（`expires_at`），過期金鑰自動失效
- 建議每 90 天輪換金鑰

**金鑰 CRUD API（3.4 節「API 金鑰管理」子表）：**

| Method | Path | 說明 | 參數 |
|--------|------|------|------|
| GET | `/api/v1/auth/keys` | 列出金鑰（不含 hash） | `page`, `limit`, `is_active` |
| POST | `/api/v1/auth/keys` | 建立金鑰（回傳明文字串僅一次） | `name`, `expires_at` |
| PUT | `/api/v1/auth/keys/:id` | 更新金鑰（啟用/停用） | `is_active`, `expires_at` |
| DELETE | `/api/v1/auth/keys/:id` | 刪除金鑰 | - |

**環境變數：**
- `API_KEY`：預設金鑰（32 字元以上隨機字串，必填或透過 `/api/v1/auth/keys` 建立）
- `API_KEY_ROTATION_DAYS`：建議輪換週期，預設 `90`
- `API_KEY_MAX_COUNT`：最大金鑰數量，預設 `10`

### 19.2 上傳與限流控制

**限制設定：**
| 環境變數 | 預設值 | 說明 |
|----------|--------|------|
| `MAX_UPLOAD_SIZE_MB` | `500` | 單檔上傳上限 |
| `CHUNKED_UPLOAD_THRESHOLD_MB` | `100` | 超過此值必須使用分片上傳 |
| `RATE_LIMIT_PER_MINUTE` | `30` | 每分鐘請求上限（全域預設） |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | 滑動視窗大小 |
| `WS_MAX_MESSAGE_SIZE_MB` | `50` | WS 單條訊息上限 |
| `WS_MAX_CONNECTIONS_PER_KEY` | `10` | 單金鑰最大同時 WS 連線數 |

**MIME type 實際校驗：**
1. 使用 `python-magic`（libmagic Python 封裝）進行 magic bytes 檢測，不依賴副檔名
2. 白名單驗證：檢測結果必須落在 `audio/*` 或 `video/*` 範圍內，否則拒絕上傳並回傳 HTTP 400
3. 上傳後以 UUID v4 重新命名儲存（不使用原始檔名），避免路徑穿越與檔案覆蓋攻擊
4. `audio_files` 表增加 `verified_mime_type` 欄位，記錄 magic bytes 檢測結果

**Dockerfile 依賴：** requirements 增加 `python-magic` 套件（需系統安裝 `libmagic1`）

### 19.2.1 Rate Limiting 演算法

**演算法：** Sliding Window Counter（滑動視窗計數器），平衡 fixed window 的突發允許與 token bucket 的實作複雜度。

**儲存後端：**
- V1：記憶體（`slowapi` 預設 in-memory backend），workers=1 下足以保證一致性
- V2（升級為多 worker / 多容器）：Redis backend（`slowapi[redis]`），key 格式 `ratelimit:<api_key_id>:<window_start>`

**限流維度：**
- 每 API 金鑰每分鐘最多 `RATE_LIMIT_PER_MINUTE` 次請求
- 個別金鑰可透過 `api_keys.rate_limit_override` 覆寫（例如質檢端設為 300）
- WebSocket 訊息獨立計算：單金鑰每秒 30 條訊息上限

**端點分組與權重：**

| 端點群組 | 權重 |
|----------|------|
| 健康檢查、metadata 查詢 | 0（不計入） |
| 一般 GET（列表、詳情） | 1 |
| 一般 POST（建立資源） | 1 |
| ASR `/transcribe`、批次辨識 | 5（消耗 GPU 資源） |
| Fine-tune 建立任務 | 10 |
| YouTube 下載 | 3 |

**超限行為：**
- HTTP 429 + `Retry-After` header（秒數，依視窗剩餘時間計算）
- response 包含當前用量：
  ```json
  {
    "success": false,
    "data": null,
    "error": {
      "code": "SYSTEM_RATE_LIMIT_EXCEEDED",
      "message": "請求頻率超出限制",
      "details": {"limit": 30, "used": 31, "window_seconds": 60, "retry_after_seconds": 42}
    }
  }
  ```

### 19.3 CORS 配置
| 環境變數 | 預設值 | 說明 |
|----------|--------|------|
| `CORS_ORIGINS` | `http://localhost:3000` | 允許的前端來源（逗號分隔） |

**生產環境強制要求：**
- 不得使用 `*`（萬用字元）
- 啟動時若偵測 `CORS_ORIGINS=*` 且 `ENV=production`，拒絕啟動並回報錯誤
- `CORS_ALLOW_CREDENTIALS=true` 時，`CORS_ORIGINS` 必須為具體網域清單

### 19.3.1 安全標頭 (Security Headers)

下列 header 必須由後端 middleware 自動加入所有回應：

| Header | 值 | 用途 |
|--------|-----|------|
| `Strict-Transport-Security` | `max-age=63072000; includeSubDomains; preload` | HSTS，強制 HTTPS |
| `X-Content-Type-Options` | `nosniff` | 防 MIME sniffing |
| `X-Frame-Options` | `DENY` | 防 clickjacking |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | 限制 referrer 洩漏 |
| `Permissions-Policy` | `geolocation=(), camera=(), microphone=()` | 限制瀏覽器 API |
| `Content-Security-Policy` | 見下方 | XSS 防護 |

**Content-Security-Policy（前端 Next.js Middleware）：**
```
default-src 'self';
script-src 'self' 'nonce-{nonce}';
style-src 'self' 'unsafe-inline' https://fonts.googleapis.com;
font-src 'self' https://fonts.gstatic.com data:;
img-src 'self' data: blob:;
media-src 'self' blob:;
connect-src 'self' https://${NEXT_PUBLIC_API_HOST} wss://${NEXT_PUBLIC_API_HOST};
frame-ancestors 'none';
base-uri 'self';
form-action 'self';
```
- nonce 每請求動態生成，由 Next.js Middleware 注入 inline script
- 違規回報透過 `report-uri /api/v1/csp-report`（僅 dev 環境，prod 移除避免額外攻擊面）

### 19.3.2 OpenAPI 文檔處置

| 端點 | 開發環境 | 生產環境 |
|------|---------|---------|
| `/api/v1/docs`（Swagger UI） | 啟用，無需認證 | 啟用但限 `admin` scope |
| `/api/v1/redoc` | 啟用，無需認證 | 停用（透過 `OPENAPI_DOCS_ENABLED=false`） |
| `/api/v1/openapi.json` | 啟用 | 啟用但限 `admin` scope |

**環境變數：**
- `OPENAPI_DOCS_ENABLED`：是否啟用文檔端點（預設 `true`）
- `OPENAPI_DOCS_REQUIRE_AUTH`：是否要求認證（預設 `false`，prod 強制 `true`）
- 違反 `prod + 未認證` 組合 → 啟動時報錯

### 19.4 資料加密策略

**背景：** 音檔與逐字稿可能包含敏感語音內容（會議紀錄、客服錄音等），需依合規需求實施加密。

**短期方案（V1 可實施）：**
- Docker volume 層級使用 LUKS（Linux Unified Key Setup）對 `/data/audio` 與 `/data/postgres` 進行區塊層加密
- 適用場景：Linux 部署環境，volume 為實體磁碟或 LVM 分割區
- 限制：Windows 開發環境不支援 LUKS，開發階段以檔案系統權限控管代替

**中期方案（V2 實施）：**
- 音檔儲存時以 AES-256-GCM 加密，金鑰透過 `ENCRYPTION_KEY` 環境變數管理（64 字元 hex 字串 = 256 位元金鑰）
- 逐字稿文字欄位（`transcript_text`、`normalized_text`）可選啟用 AES-256-GCM 欄位級加密
- 加密/解密在 FastAPI 層透明進行：上傳時加密後寫入磁碟，下載/處理時解密後送入管線
- 金鑰輪換：支援雙金鑰過渡期，新金鑰加密新資料，舊金鑰解密舊資料，漸進式遷移

**資料庫連線加密：**
- PostgreSQL 連線啟用 TLS：`DATABASE_URL` 中設定 `sslmode=require`
- 環境變數 `DB_SSLMODE` 預設為 `require`，開發環境可覆寫為 `disable`

**金鑰管理：**
- `ENCRYPTION_KEY` 透過環境變數注入，不寫入程式碼或 `.env` 檔案
- 生產環境建議升級至金鑰管理服務（如 HashiCorp Vault、AWS KMS）
- 金鑰遺失將導致加密資料無法解密，需建立金鑰備份與災難恢復流程

---

## 二十、CI/CD 流程

### 20.1 持續整合（GitHub Actions）

**觸發條件：** PR 建立或更新時

**執行流程（依序）：**

| 階段 | 工具 | 失敗判定 |
|------|------|---------|
| 1. 後端 Lint | `ruff check`、`ruff format --check` | 任一錯誤 |
| 2. 後端型別 | `mypy --strict` | 任一型別錯誤 |
| 3. 前端 Lint | `eslint`、`prettier --check` | 任一錯誤 |
| 4. 前端型別 | `tsc --noEmit` | 任一型別錯誤 |
| 5. 後端單元測試 | `pytest tests/unit/ --cov=app --cov-fail-under=70` | 覆蓋率 < 70% 或任一失敗 |
| 6. 前端單元測試 | `vitest run --coverage` | 覆蓋率 < 70% 或任一失敗 |
| 7. 資料庫遷移測試 | `alembic upgrade head && alembic downgrade base && alembic upgrade head` | 任一 migration 失敗 |
| 8. API contract 測試 | `openapi-typescript` 比對前後端 schema | 不一致 |
| 9. 整合測試 | `pytest tests/integration/`（PostgreSQL testcontainer） | 任一失敗 |
| 10. E2E 測試 | `playwright test --project=chromium`（核心流程） | 任一失敗 |
| 11. 安全掃描 | `trivy image asr-backend:latest --severity HIGH,CRITICAL --exit-code 1` | 發現 HIGH/CRITICAL CVE |
| 12. 依賴授權審計 | `pip-licenses --fail-on='GPL'`、`license-checker` | 偵測禁用授權 |
| 13. Secret 掃描 | `gitleaks detect --no-banner` | 偵測 hardcoded secret |

**閾值：** 所有檢查通過才可 merge 到 master。E2E 測試在 PR 階段執行核心流程（離線辨識 + 校正工作台），完整套件在每日排程執行。

### 20.2 持續部署

**觸發條件：** merge 到 master 分支

**執行流程：**
1. 建構 Docker 映像（後端 + 前端）
2. 推送至容器 Registry（Docker Hub / 私有 Registry）
3. 生產環境拉取新映像並重新啟動容器

### 20.3 環境變數

| 變數 | 用途 |
|------|------|
| `DOCKER_REGISTRY` | 容器 Registry 地址 |
| `IMAGE_TAG` | 映像標籤（預設 git SHA） |

---

## 二十一、Docker 容器化與服務編排 (Docker Compose)

為確保在多 GPU 節點環境中的穩定性，系統強制採用 Docker Compose 進行部署，並依賴 NVIDIA Container Toolkit。

### 21.1 生產級 `docker-compose.yml` 範本

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:16-alpine
    restart: always
    env_file: .env
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5

  backend:
    build:
      context: ./backend
      target: production
    restart: always
    env_file: .env
    depends_on:
      postgres:
        condition: service_healthy
    ports:
      - "8000:8000"
    volumes:
      - model_cache:/data/models
      - audio_storage:/data/audio
    # 解決 PyTorch DataLoader 記憶體不足問題
    shm_size: '8gb'
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s

  frontend:
    build:
      context: ./frontend
      target: production
    restart: always
    env_file: .env
    depends_on:
      backend:
        condition: service_healthy
    ports:
      - "3000:3000"

volumes:
  postgres_data:
  model_cache:
  audio_storage:
```

### 21.2 多階段建構策略 (Multi-Stage Builds)

為縮減映像檔體積並強化安全（Attack Surface Reduction），前後端 Dockerfile 必須採用 Multi-Stage 策略：
- **Backend**: 將 `pip install` 編譯依賴放在 `builder` 階段，運行階段的映像檔只複製編譯好的虛擬環境（或 wheels），避免在生產映像檔中保留編譯器與快取。
- **Frontend**: 遵循 Next.js 官方 standalone 模式，`builder` 階段執行 `npm run build`，`runner` 階段僅複製 `.next/standalone` 與 `.next/static` 資料夾，映像檔大小可控制在 150MB 以內。

### 21.3 快取與 Volume 隔離策略
- **model_cache**: 綁定至 `/data/models`。由於 ASR 模型與 vLLM 權重高達十幾 GB，必須掛載為外部 Volume。嚴禁將權重包裝入 Docker 映像檔中。
- **audio_storage**: 綁定至 `/data/audio`。確保持久化保存使用者音檔，即使容器銷毀，音檔與訓練資料亦不遺失。

---

## 二十二、可觀測性 (Observability)

### 22.1 結構化日誌（Structured Logging）

**格式：** 強制使用 JSON Lines，每行為一條完整 JSON 物件。輸出至 stdout，由 Docker `json-file` driver 統一回收。

**必含欄位：**

| 欄位 | 類型 | 說明 |
|------|------|------|
| `timestamp` | ISO 8601 | UTC 時間，毫秒精度 |
| `level` | string | `DEBUG` / `INFO` / `WARNING` / `ERROR` / `CRITICAL` |
| `service` | string | `asr-backend` / `asr-frontend` |
| `trace_id` | string | OpenTelemetry trace ID（16 bytes hex） |
| `span_id` | string | OpenTelemetry span ID（8 bytes hex） |
| `request_id` | string | UUID v4，每個 HTTP 請求 / WS 訊息一個 |
| `api_key_id` | int | 已認證請求的金鑰 ID（未認證為 null） |
| `endpoint` | string | 路徑或 WS action 名稱 |
| `method` | string | HTTP method 或 `ws.<action>` |
| `status_code` | int | HTTP 狀態碼（WS 為 close code） |
| `duration_ms` | float | 端到端處理耗時 |
| `model_version` | string | 推理使用的模型版本（ASR/Aligner 路徑） |
| `message` | string | 簡短訊息（人類可讀） |
| `error_code` | string | 錯誤碼（對應附錄 A 字典），成功時 null |
| `extra` | object | 模組自訂欄位（如 `vram_used_mb`、`queue_depth`） |

**範例：**
```json
{"timestamp":"2026-05-15T08:42:13.124Z","level":"INFO","service":"asr-backend","trace_id":"4bf92f3577b34da6a3ce929d0e0e4736","span_id":"00f067aa0ba902b7","request_id":"f47ac10b-58cc-4372-a567-0e02b2c3d479","api_key_id":3,"endpoint":"/api/v1/asr/transcribe","method":"POST","status_code":200,"duration_ms":3142.7,"model_version":"Qwen3-ASR-1.7B@2026-04-01","message":"transcription completed","error_code":null,"extra":{"audio_duration_sec":120.4,"vram_used_mb":4892}}
```

### 22.2 敏感資料過濾規則

下列內容**絕對禁止**寫入日誌：

- Bearer token 原文（即便雜湊後也禁止）
- 音檔 base64 內容（質檢 WS 請求須在記錄前剝除 `audio` 欄位）
- 辨識結果文字（`transcript_text`、`normalized_text`、`corrected_text`）
- 使用者上傳的原始檔名（可能含 PII）— 改記錄 UUID 重命名後的儲存名
- 資料庫連線字串中的密碼
- `ENCRYPTION_KEY`、`API_KEY`、`HF_TOKEN`、`DB_PASSWORD` 等任何 secret

**實作：** 在 Python logging filter 層攔截，依關鍵字白名單 / 黑名單過濾。提供 `redact_dict(payload, keys=[...])` 工具函式。

### 22.3 日誌等級準則

| 等級 | 使用情境 |
|------|---------|
| DEBUG | 模型載入細節、VAD 切點、KenLM 候選詞、僅 dev 環境啟用 |
| INFO | 請求受理、辨識完成、訓練 epoch 結束 |
| WARNING | 後處理可選步驟跳過、Hotword 群組未啟用、上採樣警告 |
| ERROR | 單一請求失敗、模型推理 OOM 重試、yt-dlp 下載失敗 |
| CRITICAL | 必載模型載入失敗、資料庫連線中斷、GPU 不可用 |

生產環境預設 `LOG_LEVEL=INFO`，可透過環境變數調整為 `DEBUG`（除錯模式）。

### 22.4 日誌保留策略

| 等級 | 保留期 | 儲存位置 |
|------|--------|---------|
| DEBUG | 1 天 | 容器 stdout（Docker rotate） |
| INFO / WARNING | 30 天 | 容器 stdout + log shipping 至外部聚合（Loki / ELK） |
| ERROR / CRITICAL | 365 天 | 外部聚合 + 告警通道（Slack / Email） |
| 審計日誌（authn / authz 事件） | 730 天 | 獨立資料表 `audit_logs`，符合 25 節合規要求 |

Docker `json-file` log driver 配置 `max-size: 10m, max-file: 5`（已於 7.1 節定義）。外部 log shipping 不在 V1 強制範圍，但程式需支援切換（透過 `LOG_FORMAT=json` 環境變數，無侵入式整合）。

### 22.5 Prometheus 指標（Metrics）

**端點：** `GET /metrics`（**僅綁定 internal network，不可暴露至外部**；豁免認證但限本機與內部監控系統存取）。

**指標清單：**

| 指標名稱 | 類型 | 標籤 | 說明 |
|----------|------|------|------|
| `asr_inference_duration_seconds` | Histogram | `model`, `language` | 單次 ASR 推理耗時分佈 |
| `asr_inference_total` | Counter | `model`, `status` | 累積推理次數（status: success/failed/oom） |
| `asr_audio_duration_seconds_total` | Counter | `model`, `source` | 累積處理的音檔總時長 |
| `gpu_vram_used_bytes` | Gauge | `device` | 當前 VRAM 使用量 |
| `gpu_vram_total_bytes` | Gauge | `device` | 總 VRAM |
| `gpu_utilization_pct` | Gauge | `device` | GPU 利用率 |
| `queue_depth` | Gauge | `priority` | 佇列深度（priority: realtime/batch） |
| `queue_wait_seconds` | Histogram | `priority` | 佇列等待時間分佈 |
| `model_load_status` | Gauge | `model`, `slot` | 模型載入狀態（1 = loaded, 0 = unloaded, -1 = failed） |
| `finetune_running_count` | Gauge | - | 進行中訓練任務數 |
| `finetune_progress_pct` | Gauge | `task_id` | 訓練進度百分比 |
| `ws_connections_active` | Gauge | - | 當前活躍 WebSocket 連線數 |
| `http_requests_total` | Counter | `method`, `endpoint`, `status_code` | HTTP 請求總數 |
| `http_request_duration_seconds` | Histogram | `method`, `endpoint` | HTTP 請求延遲分佈 |
| `auth_failures_total` | Counter | `reason` | 認證失敗次數（reason: invalid_key/expired/insufficient_scope） |
| `rate_limit_exceeded_total` | Counter | `api_key_id` | 觸發限流次數 |

### 22.6 Distributed Tracing（OpenTelemetry）

**目的：** 音檔處理鏈長（VAD → ASR → Aligner → Diarization → Correction），單一請求耗時異常時需快速定位瓶頸 stage。

**實作：**
- 後端使用 `opentelemetry-instrumentation-fastapi`、`opentelemetry-instrumentation-sqlalchemy` 自動 instrumentation
- 推理管線每個 stage 手動建立 span：`vad.detect`、`asr.transcribe`、`aligner.align`、`diarization.run`、`correction.pipeline`
- `trace_id` 透過 `traceparent` HTTP header（W3C Trace Context）傳遞
- SSE 事件與 WS 訊息夾帶 `trace_id`，前端可在 React Query devtools 內查看完整 trace

**Exporter：**
- V1 預設 OTLP gRPC → 本機 Jaeger / Tempo（可選，透過 `OTEL_EXPORTER_OTLP_ENDPOINT` 啟用）
- 未設定 endpoint 時 fallback 為 console exporter（dev 環境用）

**取樣率：**
- 正式環境 head-based sampling 10%
- 錯誤請求（`status_code >= 500`）強制取樣 100%（tail-based）
- 透過 `OTEL_TRACES_SAMPLER_ARG=0.1` 調整

### 22.7 環境變數

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `LOG_LEVEL` | `INFO` | 日誌等級 |
| `LOG_FORMAT` | `json` | 日誌格式（`json` / `text`） |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | - | OTLP 接收端（空值則停用 tracing） |
| `OTEL_SERVICE_NAME` | `asr-backend` | OpenTelemetry 服務名稱 |
| `OTEL_TRACES_SAMPLER_ARG` | `0.1` | tracing 取樣率 |
| `METRICS_ENABLED` | `true` | 是否啟用 `/metrics` 端點 |

---

## 二十三、服務水準目標 (SLO / SLA)

### 23.1 服務水準目標（SLO）

| 指標 | 目標 | 衡量視窗 | 衡量方式 |
|------|------|---------|---------|
| 可用率（Availability） | 99.5%（Client Profile）/ 99.0%（Vendor Profile） | 每月 | `/health` 通過率 |
| ASR 推理 P95 延遲（單檔 ≤ 5 分鐘） | ≤ 1.5 × 音檔時長 | 每週 | `asr_inference_duration_seconds` histogram |
| ASR 推理 P99 延遲（單檔 ≤ 5 分鐘） | ≤ 2.5 × 音檔時長 | 每週 | 同上 |
| 質檢 WS 端到端延遲 P95（5 秒以內音檔） | ≤ 3 秒 | 每週 | WS 訊息送出至 result 回傳 |
| 佇列等待時間 P95 | ≤ 10 秒（realtime）/ 5 分鐘（batch） | 每日 | `queue_wait_seconds` histogram |
| 模型切換中斷時間 | 0 秒（zero-downtime） | 每次切換 | 進行中任務失敗率 |
| Fine-tune 任務完成率 | ≥ 95% | 每月 | 完成 / （完成 + 失敗） |

### 23.2 容量規劃基準（48 GB GPU，單節點）

| 場景 | 預期吞吐量 |
|------|-----------|
| Client Profile，純推理 | ≥ 30 倍即時率（30 分鐘音檔在 1 分鐘內完成） |
| Vendor Profile（Fine-tune 進行中） | ≥ 5 倍即時率（推理 batch_size=1） |
| 質檢 WS 並發連線 | ≥ 50 條（每條 < 5 秒音檔） |
| 同時佇列任務上限 | 20（受 `MAX_QUEUE_SIZE` 限制） |

### 23.3 SLA 違規告警

- 連續 3 個衡量視窗未達 SLO → 自動建立 incident（透過 Webhook 通知）
- 可用率 < 95% / 月 → 觸發 P0 incident 並通知值班人員
- VRAM 持續 > 90% 超過 10 分鐘 → 觸發容量告警

### 23.4 環境變數

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `SLO_ALERT_WEBHOOK_URL` | - | 違規通知 Webhook（Slack / Teams / DingTalk） |
| `SLO_AVAILABILITY_TARGET` | `0.995` | 可用率目標 |

---

## 二十四、災難復原 (Disaster Recovery)

### 24.1 備份目標（RPO / RTO）

| 資料類別 | RPO | RTO | 備份策略 |
|---------|-----|-----|---------|
| PostgreSQL（含 transcriptions、api_keys、correction_segments） | 24 小時 | 4 小時 | 每日 `pg_basebackup` 全量 + WAL 歸檔 |
| Fine-tune Checkpoints | 7 天 | 24 小時 | 訓練完成時複製最佳 checkpoint 至異地 |
| 音檔（`/data/audio`） | 7 天 | 48 小時 | 每日 rsync 至備援儲存（可選） |
| Hotword 群組與詞彙 | 24 小時 | 4 小時 | 含於 PostgreSQL 備份 |
| API 金鑰 | 即時 | 1 小時 | 含於 PostgreSQL 備份 + 必要時手動重建 |
| 模型權重 | 不適用 | 4 小時 | 可從 HuggingFace 重新下載 |

### 24.2 PostgreSQL 備份策略

**每日全量備份：**
```bash
# 透過 cron 排程
pg_basebackup -h postgres -U asr_user -D /backup/$(date +%Y%m%d) \
  -Ft -z -P -X stream --slot=backup_slot
```

**WAL 歸檔（point-in-time recovery）：**
- `archive_mode = on`
- `archive_command = 'rsync %p backup-host:/wal/%f'`
- 保留 7 天 WAL，支援精確到秒的時點還原

**備份驗證：**
- 每週自動執行 restore drill：從最新備份還原至測試資料庫，驗證可開啟
- 結果寫入 `audit_logs`，違規觸發告警

### 24.3 Checkpoint 備份策略

- Fine-tune 完成時，將 `best_checkpoint` 透過 `rclone` 同步至異地物件儲存（S3 / MinIO）
- 保留週期：每個訓練任務的最佳 checkpoint 保留 90 天
- 進行中的 checkpoint 不備份（過大 + 可重訓）
- 環境變數 `CHECKPOINT_BACKUP_TARGET`（e.g. `s3://backup-bucket/checkpoints/`）

### 24.4 音檔備份策略（可選）

- 預設**不備份**音檔（依個資合規傾向，音檔屬最敏感資料，外部複本增加風險面）
- 啟用條件：客戶簽署資料處理協議並要求備份時
- 啟用方式：`AUDIO_BACKUP_ENABLED=true` + `AUDIO_BACKUP_TARGET=<rclone remote>`
- 備份必須符合 19.4 節加密策略（傳輸與靜態皆加密）

### 24.5 災難復原演練

- 每季至少執行一次完整 DR drill：
  1. 在備援環境從備份還原 PostgreSQL
  2. 重新下載模型權重
  3. 啟動服務，執行健康檢查
  4. 記錄 RTO 實測值，若超出目標 → 改善流程
- 演練紀錄寫入 `audit_logs`，並產出報告供管理層審閱

### 24.6 環境變數

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `PG_BACKUP_SCHEDULE` | `0 2 * * *` | PostgreSQL 備份排程 |
| `PG_BACKUP_TARGET` | `/backup/postgres` | 備份儲存路徑 |
| `PG_BACKUP_RETENTION_DAYS` | `30` | 備份保留天數 |
| `CHECKPOINT_BACKUP_TARGET` | - | Checkpoint 異地備份 rclone target |
| `AUDIO_BACKUP_ENABLED` | `false` | 是否啟用音檔備份 |
| `AUDIO_BACKUP_TARGET` | - | 音檔備份 rclone target |

---

## 二十五、個資合規與資料保留 (Privacy & Data Retention)

### 25.1 合規依據

本平台處理音檔（內含語音生物特徵）、逐字稿（可能含個人身分資訊），須符合下列法規：

- 台灣《個人資料保護法》第 3 條（當事人權利）、第 10 條（請求權）、第 11 條（更正、刪除）
- 歐盟 GDPR Article 15（存取權）、Article 17（被遺忘權）、Article 20（資料可攜權）— 適用於跨境客戶
- 客戶資料處理協議（DPA）— 依個案簽署

### 25.2 資料分類

| 類別 | 範例 | 預設保留期 | 加密要求 |
|------|------|-----------|---------|
| 高敏感 | 音檔原始內容、verified_mime_type、原始檔名 | `AUDIO_RETENTION_DAYS=30` | LUKS（V1）+ AES-256-GCM（V2） |
| 中敏感 | 逐字稿文字、校正內容、語者標籤 | 90 天 | 欄位級加密（V2 可選） |
| 低敏感 | 任務 metadata、loss 曲線、佇列狀態 | 365 天 | 標準傳輸加密 |
| 審計類 | authn/authz 事件、模型切換紀錄、DR 演練紀錄 | 730 天 | 標準傳輸加密 |

### 25.3 當事人權利 API

| Method | Path | Scope | 用途 |
|--------|------|-------|------|
| GET | `/api/v1/auth/keys/:id/data-export` | `admin` 或本金鑰 | 匯出該金鑰所有關聯資料（GDPR Article 20） |
| DELETE | `/api/v1/auth/keys/:id/erase` | `admin` | 徹底刪除金鑰與所有關聯資料（GDPR Article 17） |
| GET | `/api/v1/auth/keys/:id/data-summary` | `admin` 或本金鑰 | 列出資料筆數、儲存量、保留到期日 |

**`data-export` 回傳結構：**
```json
{
  "success": true,
  "data": {
    "export_id": "uuid",
    "status": "preparing",
    "estimated_size_mb": 1024,
    "download_url": null,
    "expires_at": "2026-05-22T00:00:00Z"
  }
}
```
- 非同步產生 zip（含 PostgreSQL 匯出 + 音檔），完成後透過 SSE 推送 `data:export:complete` 事件
- 下載連結帶 24 小時短效簽章，避免長期暴露

**`erase` 流程：**
1. 標記 `api_keys.deleted_at = NOW()`
2. 刪除所有 `transcriptions`、`audio_files`、`correction_sessions`、`correction_segments`、`finetune_tasks` 中 `api_key_id` 匹配的記錄
3. 從 `/data/audio/`、`/data/checkpoints/` 移除實體檔案
4. `audit_logs` 記錄完整刪除清單（依法令需保留刪除證明）
5. **不可回復**，前端須以 modal 確認三次

### 25.4 自動清理機制

- 每日 03:00 執行（受 `DISK_CLEANUP_SCHEDULE` 控制）
- 刪除 `audio_files.created_at < NOW() - AUDIO_RETENTION_DAYS` 的實體檔案，但保留 metadata（`transcriptions` 文字結果仍可查）
- 若客戶設定 `AUDIO_RETENTION_DAYS=0` → 永久保留（需簽署 DPA 例外）

### 25.5 audit_logs 表

| 欄位 | 類型 | 說明 |
|------|------|------|
| id | BIGSERIAL PK | 主鍵 |
| event_type | VARCHAR(50) | 事件類型（見下表） |
| api_key_id | INTEGER NULL | 觸發者金鑰（系統事件為 NULL） |
| target_api_key_id | INTEGER NULL | 目標金鑰（admin 操作他人資料時） |
| ip_address | INET | 來源 IP |
| user_agent | TEXT | User-Agent |
| metadata | JSONB | 事件細節（含被影響的資源 ID 清單） |
| created_at | TIMESTAMP WITH TIME ZONE | 事件時間 |

**事件類型清單：**

| event_type | 觸發時機 |
|-----------|---------|
| `auth.login_success` | API 金鑰驗證成功（每連線一次） |
| `auth.login_failed` | 認證失敗 |
| `auth.key_created` | 建立新金鑰 |
| `auth.key_deleted` | 軟刪除金鑰 |
| `auth.key_erased` | 徹底刪除金鑰（含資料） |
| `data.export_requested` | 當事人匯出請求 |
| `data.erase_executed` | 當事人刪除執行 |
| `model.switched` | 模型切換 |
| `model.loaded` / `model.unloaded` | 模型載入 / 卸載 |
| `dr.backup_completed` | 備份完成 |
| `dr.drill_executed` | DR 演練執行 |

### 25.6 環境變數

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `AUDIT_LOG_RETENTION_DAYS` | `730` | 審計日誌保留天數 |
| `DATA_EXPORT_URL_TTL_HOURS` | `24` | 匯出下載連結有效期 |
| `ERASE_CONFIRMATION_REQUIRED` | `true` | 是否要求前端三次確認 |

---

## 二十六、第三方授權清單 (License Compliance)

### 26.1 模型權重授權

| 模型 | 授權條款 | 商業使用 | 備註 |
|------|----------|---------|------|
| Qwen3-ASR-1.7B | Apache 2.0（程式） + Qwen Research License（權重） | 條件式允許 | 需在 HuggingFace 接受授權，禁止用於違反當地法律的場景 |
| Qwen3-ASR-0.6B | 同上 | 同上 | - |
| Qwen3-ForcedAligner-0.6B | 同上 | 同上 | - |
| Qwen2.5-7B（LLM 糾錯） | 同上 | 同上 | INT4 量化版需自行轉換或下載 bitsandbytes 預量化版 |
| pyannote.audio v3.x | MIT（程式） + 需 HF 接受授權（權重） | 條件式允許 | 商業用 SaaS 需與 pyannoteAI 聯繫 |
| FireRedVAD | Apache 2.0 | 允許 | - |
| ClearVoice | Apache 2.0 | 允許 | - |
| Generative-Annotation-NEC | Apache 2.0 | 允許 | - |

### 26.2 關鍵套件授權

| 套件 | 授權 | 風險 |
|------|------|------|
| vLLM | Apache 2.0 | 無 |
| FastAPI | MIT | 無 |
| Uvicorn | BSD-3-Clause | 無 |
| PyTorch | BSD-3-Clause | 無 |
| Transformers | Apache 2.0 | 無 |
| torchaudio | BSD-2-Clause | 無 |
| yt-dlp | Unlicense（Public Domain） | 無 |
| OpenCC | Apache 2.0 | 無 |
| jieba | MIT | 無 |
| audiomentations | MIT | 無 |
| KenLM | LGPL 2.1 | 需以動態連結方式使用，不修改原始碼 |
| Next.js | MIT | 無 |
| Radix UI | MIT | 無 |
| wavesurfer.js | BSD-3-Clause | 無 |
| TanStack Query | MIT | 無 |
| Recharts | MIT | 無 |

### 26.3 資料集授權

| 資料集 | 授權 | 用途 |
|---------|------|------|
| OpenSLR RIRS_NOISES | CC-BY 4.0 | 資料增強（背景噪音 + RIR） |

### 26.4 客戶端責任聲明

部署本平台前，客戶必須：

1. 在 HuggingFace 接受所有 Qwen 系列、pyannote.audio 的個別授權條款
2. 簽署 README 內附的「第三方授權聲明」確認書
3. 若用於對外提供 SaaS 服務，須自行向 pyannoteAI 取得商業授權
4. 不得將模型權重重新分發至公開儲存庫

部署腳本啟動時，會檢查 `THIRD_PARTY_LICENSE_ACK=true` 環境變數，未設定則拒絕啟動並列出待簽署清單。

---

## 附錄 A：錯誤碼字典 (Error Code Dictionary)

### A.1 錯誤碼命名規則

- 全大寫 + 底線分隔（例：`AUTH_INVALID_KEY`）
- 前綴依領域分組：`AUTH_`、`ASR_`、`FINETUNE_`、`HOTWORD_`、`DATASET_`、`UPLOAD_`、`VALIDATION_`、`MODEL_`、`GPU_`、`QUEUE_`、`STORAGE_`、`SYSTEM_`、`IDEMPOTENCY_`、`CORRECTION_`
- 對應 HTTP 狀態碼與預設使用者訊息（繁體中文，前端可覆寫）

### A.2 認證與授權

| 錯誤碼 | HTTP | 使用者訊息 | 觸發情境 |
|--------|------|------------|---------|
| `AUTH_MISSING_TOKEN` | 401 | 請先登入或提供 API 金鑰 | 缺 Authorization header |
| `AUTH_INVALID_KEY` | 401 | API 金鑰無效 | 雜湊比對失敗 |
| `AUTH_KEY_EXPIRED` | 401 | API 金鑰已過期 | `expires_at < now()` |
| `AUTH_KEY_DELETED` | 401 | API 金鑰已停用 | `deleted_at IS NOT NULL` 或 `is_active = false` |
| `AUTH_INSUFFICIENT_SCOPE` | 403 | 權限不足 | scope 未涵蓋端點所需 |
| `AUTH_WS_PROTOCOL_INVALID` | 401 | WebSocket 認證失敗 | Sec-WebSocket-Protocol 缺 bearer subprotocol |

### A.3 上傳與驗證

| 錯誤碼 | HTTP | 使用者訊息 | 觸發情境 |
|--------|------|------------|---------|
| `UPLOAD_FILE_TOO_LARGE` | 413 | 檔案超過上限（最大 {MAX_UPLOAD_SIZE_MB} MB） | 超過 `MAX_UPLOAD_SIZE_MB` |
| `UPLOAD_MIME_NOT_ALLOWED` | 400 | 不支援的檔案類型：{verified_mime_type} | python-magic 偵測結果不在白名單 |
| `UPLOAD_AUDIO_DURATION_INVALID` | 400 | 音檔時長異常 | 0 秒或讀取失敗 |
| `UPLOAD_AUDIO_FORMAT_UNSUPPORTED` | 400 | 不支援的音檔格式：{format} | 容器格式無法解碼 |
| `UPLOAD_SAMPLE_RATE_OUT_OF_RANGE` | 400 | 取樣率超出支援範圍（8 kHz - 48 kHz）：{rate} Hz | 重取樣前的範圍檢查 |
| `UPLOAD_CHUNK_OUT_OF_ORDER` | 400 | 分片上傳順序錯誤 | 缺中間片段 |
| `UPLOAD_CHUNK_HASH_MISMATCH` | 400 | 分片完整性驗證失敗 | SHA256 不符 |
| `VALIDATION_FAILED` | 422 | 請求資料驗證失敗 | Pydantic 通用錯誤 |
| `VALIDATION_FIELD_REQUIRED` | 422 | 欄位 {field} 必填 | 缺必填欄位 |
| `VALIDATION_FIELD_OUT_OF_RANGE` | 422 | 欄位 {field} 超出允許範圍 | 數值超出 min/max |

### A.4 ASR 推理

| 錯誤碼 | HTTP | 使用者訊息 | 觸發情境 |
|--------|------|------------|---------|
| `ASR_GPU_OOM` | 503 | GPU 記憶體不足，請稍後重試 | 自動降 batch size 仍 OOM（3 次） |
| `ASR_MODEL_NOT_LOADED` | 503 | ASR 模型尚未載入完成 | 啟動期間 readiness 未過 |
| `ASR_INFERENCE_FAILED` | 500 | 辨識失敗 | vLLM 推理拋例外 |
| `ASR_LANGUAGE_NOT_SUPPORTED` | 400 | 不支援的語言：{language} | language 參數未在 enum |
| `ASR_HOTWORD_GROUP_INACTIVE` | 400 | Hotword 群組 {id} 未啟用或不存在 | hotword_group_ids 含無效 ID |

### A.5 模型管理

| 錯誤碼 | HTTP | 使用者訊息 | 觸發情境 |
|--------|------|------------|---------|
| `MODEL_LOAD_FAILED` | 500 | 模型載入失敗：{reason} | 權重檔損毀、SHA256 不符、磁碟空間不足 |
| `MODEL_SWITCH_IN_PROGRESS` | 409 | 模型切換進行中，請稍後重試 | 已有切換任務 |
| `MODEL_VERSION_NOT_FOUND` | 404 | 找不到模型版本：{version} | checkpoint_id 或 model_path 無效 |
| `MODEL_FALLBACK_ENGAGED` | 200 | 主模型不可用，已自動使用備援模型 {fallback} | 警告級回應（成功，但有降級） |

### A.6 Fine-tune

| 錯誤碼 | HTTP | 使用者訊息 | 觸發情境 |
|--------|------|------------|---------|
| `FINETUNE_DATASET_INVALID` | 400 | 資料集驗證失敗：{detail} | 5.10 datasets.validation_status = invalid |
| `FINETUNE_DATASET_QUALITY_TOO_LOW` | 400 | 資料集品質評分過低（{score} < 50） | 強制要求最低品質 |
| `FINETUNE_CONCURRENT_LIMIT` | 409 | 同時間僅允許 {limit} 個訓練任務 | 已有任務進行中 |
| `FINETUNE_VRAM_INSUFFICIENT` | 503 | GPU 資源不足以啟動訓練 | 剩餘 VRAM < 訓練最小需求 |
| `FINETUNE_TASK_NOT_FOUND` | 404 | 找不到訓練任務：{id} | - |
| `FINETUNE_CHECKPOINT_NOT_FOUND` | 404 | 找不到 checkpoint：{id} | - |
| `FINETUNE_RESUME_FAILED` | 500 | 訓練恢復失敗：{reason} | checkpoint 損毀或路徑無效 |

### A.7 校正工作台

| 錯誤碼 | HTTP | 使用者訊息 | 觸發情境 |
|--------|------|------------|---------|
| `CORRECTION_SESSION_NOT_FOUND` | 404 | 找不到校正會話 | - |
| `CORRECTION_VERSION_MISMATCH` | 409 | 該段落已被其他使用者更新，請重新載入 | optimistic locking 失敗 |
| `CORRECTION_SEGMENT_NOT_FOUND` | 404 | 找不到校正段落 | - |
| `CORRECTION_EXPORT_FORMAT_UNSUPPORTED` | 400 | 不支援的匯出格式：{format} | - |

### A.8 YouTube 下載

| 錯誤碼 | HTTP | 使用者訊息 | 觸發情境 |
|--------|------|------------|---------|
| `DATASET_YOUTUBE_DOMAIN_BLOCKED` | 400 | 不允許的網域：{domain} | SSRF 白名單拒絕 |
| `DATASET_YOUTUBE_PROTOCOL_INVALID` | 400 | 僅支援 https:// 協議 | 協議不符 |
| `DATASET_YOUTUBE_URL_MALFORMED` | 400 | URL 格式不符 YouTube 規範 | 正則比對失敗 |
| `DATASET_YOUTUBE_DOWNLOAD_FAILED` | 502 | YouTube 下載失敗：{reason} | yt-dlp 拋例外 |
| `DATASET_YOUTUBE_SUBTITLES_UNAVAILABLE` | 200 | 字幕不可用，將使用 ASR 結果作為初始參考 | 警告級回應 |

### A.9 系統與資源

| 錯誤碼 | HTTP | 使用者訊息 | 觸發情境 |
|--------|------|------------|---------|
| `GPU_UNAVAILABLE` | 503 | GPU 服務暫時不可用 | nvidia-smi 失敗、CUDA error |
| `QUEUE_FULL` | 503 | 處理佇列已滿，請稍後重試 | 達 `MAX_QUEUE_SIZE` |
| `QUEUE_JOB_NOT_FOUND` | 404 | 找不到佇列任務 | - |
| `STORAGE_DISK_FULL` | 507 | 儲存空間不足 | 磁碟使用率 > 95% |
| `STORAGE_FILE_NOT_FOUND` | 404 | 找不到檔案 | 路徑無效或已被清理 |
| `SYSTEM_DATABASE_UNAVAILABLE` | 503 | 資料庫連線異常 | PostgreSQL 不可用 |
| `SYSTEM_RATE_LIMIT_EXCEEDED` | 429 | 請求頻率超出限制（{limit}/分鐘） | 觸發 rate limiting |

### A.10 冪等性

| 錯誤碼 | HTTP | 使用者訊息 | 觸發情境 |
|--------|------|------------|---------|
| `IDEMPOTENCY_KEY_IN_PROGRESS` | 409 | 相同 idempotency key 的請求處理中 | 第一次請求尚未完成 |
| `IDEMPOTENCY_KEY_PAYLOAD_MISMATCH` | 422 | idempotency key 已使用但 payload 不同 | 防止誤用同一 key |

### A.11 前端錯誤訊息對應

前端 i18n 字典必須以錯誤碼為鍵：
```typescript
const errorMessages: Record<string, string> = {
  AUTH_INVALID_KEY: 'API 金鑰無效，請重新登入',
  ASR_GPU_OOM: 'GPU 記憶體不足，建議降低批次大小或稍後重試',
  // ...
};
```
未對應的錯誤碼 → 顯示通用訊息「發生未預期的錯誤」+ `error.message` 內容。

---

**文件結束**
