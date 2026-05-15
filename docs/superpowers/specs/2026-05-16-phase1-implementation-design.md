# Qwen3-ASR Phase 1 實施設計

**建立日期：** 2026-05-16
**狀態：** 設計凍結，待寫入實作計劃
**範圍：** CLAUDE.md「實作順序建議」第 1-4 項（基礎設施 + 後端骨架 + 預處理管線 + ASR 推理引擎）
**對應規格書版本：** v1.9
**設計方法論：** superpowers brainstorming（先決策後設計，分段對齊）

---

## 0. 釐清決策摘要

| 決策維度 | 結論 | 影響 |
|---------|------|------|
| 範圍粒度 | 第一階段聚焦（實作順序 1-4） | 後續 Phase 大綱另行規劃 |
| GPU 環境 | Linux 主機含 GPU（本機或內部） | Windows 僅負責前端、DB、CPU 邏輯；GPU 服務跑 Linux |
| 完成基準（DoD） | 單元 + 整合測試 + CI | 覆蓋率全域 ≥ 70%，熱點檔案 ≥ 90% |
| 實作節奏 | 子模組為單位 commit（4 commits） | 每模組通過 DoD 後 commit |
| 設計方案 | 方案 B：核心優先 + 橫切骨架 | Phase 1 建立強制規範要求的橫切；可選 middleware 留 no-op hooks |

---

## 1. 整體架構與目錄骨架

### 1.1 Docker Compose 服務組成（Phase 1）

```
postgres（含 zhparser 自訂映像，port 5432，volume: pgdata）
asr-backend（三階段建構，單端口 8000，workers=1，GPU runtime 部署環境）
```

V1 不啟用 Redis、Prometheus、Grafana（屬 V2 或後續 Phase）。

### 1.2 Backend 目錄骨架

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI 入口、lifespan、router 註冊
│   ├── core/
│   │   ├── config.py              # pydantic-settings、ENV 載入
│   │   ├── logging.py             # JSON 結構化日誌設定
│   │   ├── security.py            # Argon2id 雜湊、Bearer Token 解析
│   │   ├── exceptions.py          # 自訂例外類別、錯誤碼對應
│   │   ├── response.py            # ResponseEnvelope schema
│   │   └── startup_checks.py      # 啟動檢查清單
│   ├── deps/
│   │   ├── auth.py                # get_current_tenant、require_scope
│   │   └── db.py                  # SQLAlchemy session DI
│   ├── middleware/
│   │   ├── request_id.py          # trace_id / request_id 注入
│   │   ├── error_handler.py       # 全域例外處理
│   │   ├── prometheus.py          # 預留 no-op（Phase 2 啟用）
│   │   ├── tracing.py             # 預留 no-op
│   │   ├── rate_limit.py          # 預留 slowapi no-op
│   │   └── idempotency.py         # 預留 no-op
│   ├── models/                    # SQLAlchemy ORM 模型
│   │   ├── base.py                # DeclarativeBase、INTEGER PK、TIMESTAMPTZ helper
│   │   ├── api_key.py
│   │   ├── audio_file.py
│   │   ├── transcription.py
│   │   └── audit_log.py
│   ├── schemas/
│   │   ├── common.py              # ResponseEnvelope、PaginationMeta
│   │   └── asr.py                 # TranscribeOptions / TranscribeData
│   ├── repositories/
│   │   ├── base.py                # TenantScopedRepository 基底
│   │   ├── api_key.py
│   │   ├── audio_file.py
│   │   ├── transcription.py
│   │   └── audit_log.py
│   ├── services/
│   │   ├── audio/
│   │   │   ├── mime.py            # python-magic MIME 校驗
│   │   │   ├── storage.py         # UUID v4 重命名、落地寫入
│   │   │   ├── resampler.py       # torchaudio / soxr 重取樣
│   │   │   └── vad.py             # FireRedVAD 包裝
│   │   ├── asr/
│   │   │   ├── engine.py          # vLLM AsyncLLMEngine 包裝
│   │   │   ├── queue.py           # QueueBackend 抽象 + AsyncioQueueBackend
│   │   │   └── transcriber.py     # 推理流程編排
│   │   └── audit.py               # audit_log 寫入 helper
│   └── routers/
│       ├── health.py              # GET /health、GET /readiness
│       └── asr.py                 # POST /api/v1/asr/transcribe
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       └── 0001_phase1_initial.py
├── tests/
│   ├── conftest.py
│   ├── unit/
│   ├── integration/
│   └── fixtures/
│       └── audio/
├── scripts/
│   └── smoke_asr.sh
├── alembic.ini
├── pyproject.toml
└── Dockerfile                     # 三階段：deps / builder / runtime
```

### 1.3 設計原則對應

| CLAUDE.md 規範 | 目錄安排 |
|----------------|---------|
| 強制規範 5（Tenant Isolation） | `repositories/base.py` 自動掛 `api_key_id` 過濾 |
| 強制規範 6（Bearer + Scope） | `deps/auth.py` 集中管理 |
| 強制規範 2（ResponseEnvelope） | `schemas/common.py` + `core/response.py` 強制 |
| 強制規範 8（MIME magic bytes） | `services/audio/mime.py` 隔離 libmagic 依賴 |
| 強制規範 20（JSON 日誌） | `core/logging.py` + `middleware/request_id.py` 配合 |
| 跨檔案決策（vLLM 取代 ProcessPool） | `services/asr/engine.py` 啟動時初始化 |
| 跨檔案決策（workers=1 單端口） | `Dockerfile` CMD 固定 |
| 跨檔案決策（佇列抽象層 V1 即定義） | `services/asr/queue.py` |

---

## 2. 四個子模組的切分與 DoD

### 2.1 整體里程碑

```
M1 ─→ M2 ─→ M3 ─→ M4
 │     │     │     │
 │     │     │     └─ ASR API 可被呼叫（GPU manual smoke 過）
 │     │     └─ 預處理管線可獨立驗證
 │     └─ 認證、tenant、DB、日誌、health 就緒
 └─ 容器化骨架就緒，可起 postgres
```

### 2.2 M1：基礎設施與容器化骨架

| 維度 | 內容 |
|------|------|
| **工作項目** | `docker-compose.yml`（postgres + asr-backend）、`.env.example`、`backend/Dockerfile`（三階段：deps / builder / runtime）、`postgres/Dockerfile`（zhparser 自訂映像）、`postgres/init.sql`（`CREATE EXTENSION zhparser`）、`.gitattributes`（強制 LF）、`.dockerignore`、`backend/pyproject.toml`（套件、ruff、mypy、pytest 配置） |
| **進入條件** | `.gitignore` 已 commit |
| **退出條件（DoD）** | (1) `docker compose up -d postgres` 啟動成功且 `\dx` 列出 zhparser；(2) `docker compose build asr-backend` 通過 CPU 階段；(3) `.env.example` 包含 Phase 1 所有變數；(4) ruff / mypy 配置可執行；(5) `.gitattributes` 解決 CRLF 警告 |
| **Commit 訊息** | `chore: 建立 docker compose 與容器化建構骨架` |

### 2.3 M2：後端骨架（FastAPI + DB + 認證 + 橫切骨架）

| 維度 | 內容 |
|------|------|
| **工作項目** | (1) FastAPI 入口 + lifespan + Settings；(2) JSON 結構化日誌；(3) Argon2id 雜湊 + Bearer Token 解析 + Scope 強制 dependency；(4) Tenant Isolation Repository 基底；(5) Alembic 初始 migration 含 4 個表格（`api_keys`、`audio_files`、`transcriptions`、`audit_logs`）；(6) ResponseEnvelope + 全域例外處理 + 錯誤碼對應；(7) `GET /health`、`GET /readiness`（檢查 DB 連線）；(8) 預留 middleware（Prometheus / tracing / slowapi / Idempotency）註冊但 no-op，並標 `@pytest.mark.phase2` |
| **進入條件** | M1 完成 |
| **退出條件（DoD）** | (1) `alembic upgrade head` 在容器內成功，所有表格 `TIMESTAMP WITH TIME ZONE`；(2) `GET /health` 回 `{"success": true, "data": {...}, "error": null}`；(3) `GET /readiness` 驗證 DB 連線；(4) Bearer Token 缺失 / scope 不符回 401 / 403，錯誤碼對應附錄 A；(5) 整合測試覆蓋：health、readiness、auth 拒絕路徑、tenant 過濾；(6) 單元測試覆蓋率 ≥ 70%（重點：security、response、tenant filter）；(7) ruff + mypy + pytest 全通過；(8) CI workflow 啟動並 pass |
| **Commit 訊息** | `feat: 建立 FastAPI 後端骨架、認證與多租戶基礎` |

### 2.4 M3：音檔預處理管線

| 維度 | 內容 |
|------|------|
| **工作項目** | (1) `python-magic` MIME 校驗（`audio/*` + `video/*` 白名單）；(2) UUID v4 檔名重寫；(3) torchaudio / soxr 重取樣（8 kHz–48 kHz → 16 kHz mono WAV）+ `resampling_warning` flag；(4) FireRedVAD 包裝（按需載入）；(5) 測試 fixtures（含 8 / 16 / 48 kHz 樣本、非音檔、副檔名作假） |
| **進入條件** | M2 完成 |
| **退出條件（DoD）** | (1) 白名單外檔案被拒絕（含「副檔名作假」對抗測試）；(2) 8 kHz 音檔正確重取樣並設定 `resampling_warning`；(3) VAD 對測試音檔輸出合理語音段；(4) 整合測試 MIME → UUID → 重取樣 → VAD 全鏈路通過；(5) 單元測試覆蓋率 ≥ 70%；(6) ruff + mypy + pytest 全通過；(7) CI 通過 |
| **Commit 訊息** | `feat: 加入音檔預處理管線（MIME 校驗、重取樣、VAD）` |

### 2.5 M4：ASR 推理引擎與 transcribe 端點

| 維度 | 內容 |
|------|------|
| **工作項目** | (1) `app/services/asr/engine.py`：vLLM AsyncLLMEngine 於 FastAPI lifespan 啟動載入；(2) `app/services/asr/queue.py`：QueueBackend 抽象 + AsyncioQueueBackend（batch 通道）；(3) `app/services/asr/transcriber.py`：編排 MIME → UUID → 儲存 → 重取樣 → VAD → ASR → 寫入 `transcriptions`（含 `model_version`、`api_key_id`、`resampling_warning`）；(4) Pydantic schema；(5) `POST /api/v1/asr/transcribe` 端點（強制 Bearer + scope `asr:write`）；(6) Mock vLLM fixture；(7) Linux GPU 環境 manual smoke 腳本 |
| **進入條件** | M3 完成、Linux + GPU 環境就緒 |
| **退出條件（DoD）** | (1) `POST /api/v1/asr/transcribe` 帶有效 Bearer + scope 成功；(2) 多租戶隔離驗證：A 金鑰無法讀取 B 金鑰的 `transcriptions`；(3) 寫入 `transcriptions` 含 `model_version`、`api_key_id`、`resampling_warning`；(4) 整合測試使用 mock vLLM，CI 通過；(5) Linux GPU 環境 manual smoke：1 分鐘音檔推理成功；(6) 單元測試覆蓋率 ≥ 70%；(7) ruff + mypy + pytest 全通過；(8) CI 通過（跳過 GPU 標籤的測試） |
| **Commit 訊息** | `feat: 整合 vLLM ASR 推理引擎與 transcribe 端點` |

---

## 3. 橫切關注點細部設計

### 3.1 認證機制（Bearer Token + Argon2id + Scope）

**Token 結構與儲存：**
- 客戶端傳遞：`Authorization: Bearer <raw_token>`
- 資料庫儲存：僅儲存 `api_keys.key_hash`（Argon2id）
- Argon2id 參數：`time_cost=3, memory_cost=65536 KiB (64 MiB), parallelism=4`

**查找策略（規格瑕疵 PHASE1-SPEC-01 補丁）：**

規格 19.1 描述「以 Argon2id 雜湊 token，查詢 `api_keys.key_hash`」實作上不可行（Argon2id 含隨機 salt，每次結果不同）。本設計補上 `lookup_prefix` 欄位：

```python
def lookup_prefix(raw_token: str) -> str:
    # HMAC-SHA256，使用環境密鑰（避免 raw_token 直接洩漏前綴）
    return hmac.new(LOOKUP_KEY, raw_token.encode(), hashlib.sha256).hexdigest()[:16]

def verify_token(raw_token: str, db: Session) -> ApiKey | None:
    prefix = lookup_prefix(raw_token)
    candidates = db.query(ApiKey).filter(
        ApiKey.lookup_prefix == prefix,
        ApiKey.deleted_at.is_(None),
        ApiKey.is_active.is_(True),
    ).all()
    for key in candidates:
        try:
            argon2_hasher.verify(key.key_hash, raw_token)
            return key
        except VerifyMismatchError:
            continue
    return None
```

**Dependency 設計：**

```python
async def get_current_tenant(
    authorization: str = Header(...),
    db: Session = Depends(get_db),
) -> ApiKey:
    if not authorization.startswith("Bearer "):
        raise UnauthorizedError(code="AUTH_MISSING_BEARER")
    token = authorization[7:]
    api_key = verify_token(token, db)
    if api_key is None:
        raise UnauthorizedError(code="AUTH_INVALID_TOKEN")
    return api_key

def require_scope(scope: str):
    async def _check(api_key: ApiKey = Depends(get_current_tenant)) -> ApiKey:
        if scope not in api_key.scopes and "admin" not in api_key.scopes:
            raise ForbiddenError(code="AUTH_SCOPE_INSUFFICIENT", scope=scope)
        return api_key
    return _check
```

**豁免規則：** 僅 `GET /health` 與 `GET /readiness` 不加 dependency。

### 3.2 多租戶隔離（Tenant Isolation Repository Pattern）

**Repository 基底：**

```python
class TenantScopedRepository(Generic[T]):
    model: type[T]

    def __init__(self, db: Session, api_key_id: int):
        self.db = db
        self.api_key_id = api_key_id

    def _scoped_query(self) -> Query:
        return self.db.query(self.model).filter(
            self.model.api_key_id == self.api_key_id
        )

    def get(self, id_: int) -> T | None:
        return self._scoped_query().filter(self.model.id == id_).one_or_none()

    def create(self, **kwargs) -> T:
        instance = self.model(**kwargs, api_key_id=self.api_key_id)
        self.db.add(instance)
        self.db.flush()
        return instance
```

**強制 lint 規則（M2 DoD 之一）：** pre-commit hook 或自訂 ruff plugin 掃描 `app/services/` 與 `app/routers/` 是否手動拼接 `api_key_id ==`。

**Phase 1 涵蓋表格：** `audio_files`、`transcriptions`。其他規範要求的表格在對應 Phase 加入時擴展。

### 3.3 JSON 結構化日誌

**Logger 工具：** structlog（序列化效能、型別友好度較佳）。

**強制欄位：** `timestamp`、`level`、`trace_id`、`request_id`、`api_key_id`、`endpoint`、`method`、`status_code`、`duration_ms`、`error_code`、`message`。

**敏感資料黑名單（強制過濾）：**
- `Authorization` header
- 音檔 base64 內容
- 辨識結果文字（`transcriptions.asr_result`、`text`）
- 原始檔名

**request_id middleware：**

```python
@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = rid
    with structlog.contextvars.bound_contextvars(request_id=rid):
        response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    return response
```

### 3.4 ResponseEnvelope 與錯誤處理

```python
class ResponseEnvelope(BaseModel, Generic[T]):
    success: bool
    data: T | None
    error: ErrorDetail | None

class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict | None = None
```

**全域例外處理器：**

```python
@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    logger.warning("Request failed", error_code=exc.code)
    return JSONResponse(
        status_code=exc.http_status,
        content=ResponseEnvelope[None](
            success=False, data=None,
            error=ErrorDetail(code=exc.code, message=exc.message, details=exc.details),
        ).model_dump(),
    )

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception")
    return JSONResponse(
        status_code=500,
        content=ResponseEnvelope[None](
            success=False, data=None,
            error=ErrorDetail(code="INTERNAL_ERROR", message="伺服器內部錯誤"),
        ).model_dump(),
    )
```

**Phase 1 錯誤碼最小集合：**

| 錯誤碼 | HTTP | 觸發 |
|--------|------|------|
| `AUTH_MISSING_BEARER` | 401 | 缺失 Bearer 標頭 |
| `AUTH_INVALID_TOKEN` | 401 | Token 不存在或已撤銷 |
| `AUTH_SCOPE_INSUFFICIENT` | 403 | scope 不符 |
| `VALIDATION_ERROR` | 422 | Pydantic schema 驗證失敗 |
| `AUDIO_MIME_INVALID` | 400 | MIME 不在白名單 |
| `AUDIO_FILE_TOO_LARGE` | 413 | 超過 `MAX_UPLOAD_SIZE_MB` |
| `AUDIO_DECODE_TIMEOUT` | 504 | torchaudio 解碼超時 |
| `AUDIO_RESAMPLE_FAILED` | 500 | 重取樣異常 |
| `AUDIO_NO_SPEECH` | 422 | VAD 找不到語音段 |
| `AUDIO_VAD_FAILED` | 500 | VAD 推理失敗 |
| `AUDIO_VAD_NOT_READY` | 503 | 服務啟動中 VAD 未載入 |
| `AUDIO_STORAGE_FAILED` | 500 | 寫入磁碟失敗 |
| `ASR_ENGINE_UNAVAILABLE` | 503 | vLLM 未載入 |
| `ASR_AUDIO_TOO_LONG` | 413 | 音檔長度 > 20 分鐘 |
| `ASR_CUDA_ERROR` | 503 | vLLM 拋 CudaError |
| `ASR_INFERENCE_FAILED` | 500 | 其他推理異常 |
| `ASR_REQUEST_TIMEOUT` | 504 | 等待 job 超時 |
| `QUEUE_FULL` | 503 | asyncio Queue 滿載 |
| `NOT_FOUND` | 404 | 資源不存在 |
| `INTERNAL_ERROR` | 500 | 未捕獲例外 |

### 3.5 預留 middleware（no-op，Phase 2 啟用）

| Middleware | Phase 1 行為 | Phase 2 行為 |
|-----------|-------------|-------------|
| `middleware/prometheus.py` | pass-through | request count / duration histogram |
| `middleware/tracing.py` | pass-through | OpenTelemetry span 建立 |
| `middleware/rate_limit.py` | pass-through | slowapi sliding window |
| `middleware/idempotency.py` | pass-through | Idempotency-Key 查重 |

每個 no-op middleware 至少有一個 `@pytest.mark.phase2` skip 測試作為 todo 標記。

---

## 4. 資料庫 Schema 與 Phase 1 Migration

### 4.1 Phase 1 表格清單（4 個，外鍵依賴順序）

```
api_keys ─→ audio_files ─→ transcriptions
   └─→ audit_logs
```

`chunked_uploads` 延後至分片上傳 Phase。

### 4.2 `api_keys`（規格書 5.9 + 規格瑕疵補丁）

| 欄位 | 類型 | 說明 |
|------|------|------|
| `id` | `SERIAL PRIMARY KEY` | 主鍵 |
| `key_hash` | `VARCHAR(255) UNIQUE NOT NULL` | Argon2id 雜湊值 |
| `lookup_prefix` | `VARCHAR(16) NOT NULL` | 規格瑕疵補丁：HMAC-SHA256 前 16 字元，做索引查找 |
| `name` | `VARCHAR(200) NOT NULL` | 金鑰名稱 |
| `description` | `TEXT` | 用途說明 |
| `scopes` | `VARCHAR(50)[] NOT NULL DEFAULT '{asr:read,asr:write}'` | Scope 清單 |
| `created_by_key_id` | `INTEGER FK NULL REFERENCES api_keys(id)` | 建立者金鑰 |
| `rate_limit_override` | `INTEGER NULL` | 個別限流覆寫 |
| `created_at` | `TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()` | 建立時間 |
| `expires_at` | `TIMESTAMP WITH TIME ZONE NULL` | 過期時間 |
| `is_active` | `BOOLEAN NOT NULL DEFAULT TRUE` | 是否啟用 |
| `deleted_at` | `TIMESTAMP WITH TIME ZONE NULL` | 軟刪除 |
| `last_used_at` | `TIMESTAMP WITH TIME ZONE NULL` | 最後使用時間 |

**索引：**

```sql
CREATE UNIQUE INDEX idx_api_keys_key_hash ON api_keys(key_hash);
CREATE INDEX idx_api_keys_active_not_deleted ON api_keys(is_active) WHERE deleted_at IS NULL;
CREATE INDEX idx_api_keys_lookup_prefix ON api_keys(lookup_prefix) WHERE deleted_at IS NULL;
```

### 4.3 `audio_files`（規格書 5.3）

| 欄位 | 類型 | 說明 |
|------|------|------|
| `id` | `SERIAL PRIMARY KEY` | 主鍵 |
| `api_key_id` | `INTEGER NOT NULL REFERENCES api_keys(id)` | 租戶隔離 |
| `original_name` | `VARCHAR(500) NOT NULL` | 原始檔名（僅顯示） |
| `storage_path` | `VARCHAR(500) NOT NULL` | UUID 重命名後路徑 |
| `file_size` | `BIGINT NOT NULL` | bytes |
| `duration_sec` | `FLOAT NULL` | 預處理後填 |
| `mime_type` | `VARCHAR(50) NULL` | 不可信 |
| `verified_mime_type` | `VARCHAR(50) NULL` | magic bytes 結果 |
| `transcription_id` | `INTEGER NULL REFERENCES transcriptions(id)` | 關聯辨識 |
| `original_sample_rate` | `INTEGER NULL` | 原始取樣率 |
| `created_at` | `TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()` | - |

**索引：**

```sql
CREATE INDEX idx_audio_files_api_key_id ON audio_files(api_key_id);
CREATE INDEX idx_audio_files_transcription_id ON audio_files(transcription_id);
```

**外鍵循環處理：** Alembic migration 內以 `op.create_foreign_key` 在兩表建立後額外加上 `audio_files.transcription_id → transcriptions.id`。

### 4.4 `transcriptions`（規格書 5.1）

| 欄位 | 類型 | 說明 |
|------|------|------|
| `id` | `SERIAL PRIMARY KEY` | 主鍵 |
| `api_key_id` | `INTEGER NOT NULL REFERENCES api_keys(id)` | 租戶隔離 |
| `file_name` | `VARCHAR(500) NULL` | 原始音檔名稱 |
| `source` | `VARCHAR(50) NOT NULL` | `upload` / `quality_ws` |
| `duration_sec` | `FLOAT NULL` | 音檔時長 |
| `language` | `VARCHAR(20) NULL` | 語言代碼 |
| `model_name` | `VARCHAR(100) NOT NULL` | 模型名稱 |
| `model_version` | `VARCHAR(50) NOT NULL` | 模型版本 |
| `transcript_text` | `TEXT NULL` | 原始逐字稿 |
| `timestamps` | `JSONB NULL` | `[{text,start,end}]` |
| `speakers` | `JSONB NULL` | Phase 1 全 NULL |
| `normalized_text` | `TEXT NULL` | Phase 1 全 NULL |
| `post_processing` | `JSONB NULL` | Phase 1 全 NULL |
| `status` | `VARCHAR(50) NOT NULL DEFAULT 'processing'` | `processing` / `completed` / `failed` |
| `processing_duration_sec` | `FLOAT NULL` | 實際耗時 |
| `error_message` | `TEXT NULL` | 錯誤訊息 |
| `hotword_group_ids` | `INTEGER[] NULL` | Phase 1 全 NULL |
| `created_at` | `TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()` | - |
| `updated_at` | `TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()` | trigger 自動更新 |

**索引：**

```sql
CREATE INDEX idx_transcriptions_api_key_id ON transcriptions(api_key_id);
CREATE INDEX idx_transcriptions_status ON transcriptions(status);
CREATE INDEX idx_transcriptions_created_at ON transcriptions(created_at DESC);
CREATE INDEX idx_transcriptions_source ON transcriptions(source);

CREATE INDEX idx_transcriptions_text_gin
  ON transcriptions USING gin(to_tsvector('chinese', transcript_text));
CREATE INDEX idx_transcriptions_normalized_text_gin
  ON transcriptions USING gin(to_tsvector('chinese', normalized_text));
```

### 4.5 `audit_logs`（規格書 25.5）

| 欄位 | 類型 | 說明 |
|------|------|------|
| `id` | `BIGSERIAL PRIMARY KEY` | 主鍵 |
| `event_type` | `VARCHAR(50) NOT NULL` | 事件類型 |
| `api_key_id` | `INTEGER NULL REFERENCES api_keys(id)` | 觸發者 |
| `target_api_key_id` | `INTEGER NULL REFERENCES api_keys(id)` | admin 操作目標 |
| `ip_address` | `INET NULL` | 來源 IP |
| `user_agent` | `TEXT NULL` | User-Agent |
| `metadata` | `JSONB NULL` | 事件細節 |
| `created_at` | `TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()` | 事件時間 |

**索引：**

```sql
CREATE INDEX idx_audit_logs_api_key_id_created ON audit_logs(api_key_id, created_at DESC);
CREATE INDEX idx_audit_logs_event_type ON audit_logs(event_type);
```

**Phase 1 寫入 event_type：** `auth.login_success`、`auth.login_failed`、`auth.key_created`、`auth.key_deleted`、`model.loaded`、`model.unloaded`、`asr.cuda_error`。

### 4.6 規格瑕疵（待 PR 修正規格書）

| 編號 | 規格章節 | 問題 | 補丁 |
|------|---------|------|------|
| PHASE1-SPEC-01 | 19.1 認證流程（line 2602） | 「以 Argon2id 雜湊 token，查詢 `api_keys.key_hash`」實作不可行（Argon2id 隨機 salt） | 補 `lookup_prefix VARCHAR(16) NOT NULL`（HMAC-SHA256 前 16 字元）作索引前置，Argon2id 僅用於最終 verify。建議先提 PR 修規格書 5.9 + 19.1 |

### 4.7 Alembic Migration 檔組織

```
backend/alembic/versions/
└── 0001_phase1_initial.py
    ├── upgrade():
    │   ├── CREATE EXTENSION IF NOT EXISTS zhparser
    │   ├── CREATE TEXT SEARCH CONFIGURATION chinese (PARSER = zhparser)
    │   ├── ALTER TEXT SEARCH CONFIGURATION chinese ADD MAPPING ...
    │   ├── op.create_table("api_keys", ...)
    │   ├── op.create_table("audio_files", ..., transcription_id 暫不建立 FK)
    │   ├── op.create_table("transcriptions", ...)
    │   ├── op.create_table("audit_logs", ...)
    │   ├── op.create_foreign_key(audio_files.transcription_id → transcriptions.id)
    │   ├── 全部索引（含 GIN）
    │   └── updated_at trigger function + transcriptions trigger
    └── downgrade(): 反向操作
```

**驗收：** `alembic upgrade head` + `alembic downgrade base` + `alembic upgrade head` 全部成功。

### 4.8 SQLAlchemy 模型基底

```python
class Base(DeclarativeBase):
    pass

class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

class UpdatedAtMixin:
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        onupdate=func.now()
    )

class TenantMixin:
    api_key_id: Mapped[int] = mapped_column(
        ForeignKey("api_keys.id"), nullable=False, index=True
    )
```

---

## 5. 預處理管線資料流

### 5.1 整體流程

```
HTTP request
   │  Content-Type: multipart/form-data
   ▼
routers/asr.py     # require_scope("asr:write")、讀取 UploadFile
   │
   ▼
services/audio/mime.py     # python-magic 校驗、白名單比對
   │  失敗 → AUDIO_MIME_INVALID (400)
   ▼
services/audio/storage.py  # UUID 重命名、寫入 AUDIO_STORAGE_DIR
   │  INSERT audio_files (storage_path, verified_mime_type, file_size, api_key_id)
   ▼
services/audio/resampler.py  # try-except + asyncio.timeout(30s)
   │  torchaudio.load → mono → 8-bit 強制 16-bit → Kaiser windowed sinc
   │  UPDATE audio_files SET original_sample_rate, duration_sec
   │  失敗 → AUDIO_RESAMPLE_FAILED / AUDIO_DECODE_TIMEOUT
   ▼
services/audio/vad.py        # FireRedVAD.detect_speech()
   │  空清單 → AUDIO_NO_SPEECH (422)
   ▼
[ 進入 M4 ASR 推理 ]
```

### 5.2 介面契約

| 步驟 | 函式簽章 | 異常碼 |
|------|---------|--------|
| MIME 校驗 | `verify_mime(buf: bytes) -> str` | `AUDIO_MIME_INVALID` |
| 儲存 | `store_upload(buf: bytes, ext: str, api_key_id: int) -> AudioFile` | `AUDIO_STORAGE_FAILED` |
| 重取樣 | `resample_to_16k_mono(src: Path) -> ResampleResult` | `AUDIO_RESAMPLE_FAILED` / `AUDIO_DECODE_TIMEOUT` |
| VAD | `detect_speech(wav_path: Path) -> list[Segment]` | `AUDIO_NO_SPEECH` / `AUDIO_VAD_FAILED` |

### 5.3 重取樣關鍵設計

```python
@dataclass
class ResampleResult:
    output_path: Path
    original_sample_rate: int
    duration_sec: float
    resampling_warning: bool   # orig_sr == 8000 為 True

async def resample_to_16k_mono(src: Path, dst_dir: Path) -> ResampleResult:
    try:
        async with asyncio.timeout(30):
            waveform, orig_sr = await asyncio.to_thread(torchaudio.load, str(src))
    except TimeoutError:
        raise AppException("AUDIO_DECODE_TIMEOUT", http_status=504)
    except Exception as e:
        raise AppException("AUDIO_RESAMPLE_FAILED", details={"reason": str(e)})

    if waveform.shape[0] > 1:
        waveform = waveform.mean(dim=0, keepdim=True)

    if waveform.dtype == torch.uint8:
        waveform = waveform.float() / 128.0 - 1.0

    if orig_sr != 16000:
        resampler = torchaudio.transforms.Resample(
            orig_freq=orig_sr,
            new_freq=16000,
            low_pass_filter_width=64,
            rolloff=0.9475937167092650,
        )
        waveform = resampler(waveform)

    out_path = dst_dir / f"{uuid4()}_16k.wav"
    await asyncio.to_thread(
        sf.write, str(out_path), waveform.squeeze().numpy(), 16000, subtype="PCM_16"
    )
    return ResampleResult(
        output_path=out_path,
        original_sample_rate=orig_sr,
        duration_sec=waveform.shape[-1] / 16000,
        resampling_warning=(orig_sr == 8000),
    )
```

### 5.4 VAD 關鍵設計

```python
class FireRedVADService:
    _model: Any = None

    @classmethod
    def load(cls, model_path: Path) -> None:
        cls._model = load_fire_red_vad(model_path)

    @classmethod
    async def detect_speech(cls, wav_path: Path) -> list[Segment]:
        if cls._model is None:
            raise AppException("AUDIO_VAD_NOT_READY", http_status=503)
        segments = await asyncio.to_thread(cls._model.infer, str(wav_path))
        if not segments:
            raise AppException("AUDIO_NO_SPEECH", http_status=422)
        return segments
```

降級備援（能量閾值法）標 `# TODO Phase 2`。

### 5.5 audio_files 兩階段寫入

```
T1: INSERT （MIME 通過、檔案落地後）
T2: UPDATE （重取樣完成後填 original_sample_rate / duration_sec）
T3: UPDATE （ASR 完成後填 transcription_id，由 M4 執行）
```

### 5.6 隔離邊界與安全考量

| 風險 | 對應 |
|------|------|
| 惡意偽造音檔造成 C++ Segfault | `asyncio.timeout(30)` + 廣域 `except Exception` |
| 副檔名偽裝 | magic bytes 校驗 |
| 路徑穿越 | UUID v4 重命名 |
| 大檔案 DoS | `MAX_UPLOAD_SIZE_MB` 限制 100 MB |
| 解碼 OOM | torchaudio 載入前 file_size 檢查（`MAX_DECODE_SIZE_MB` 500 MB） |
| 8-bit 精度異常 | 自動正規化為 16-bit float32 |

### 5.7 測試 fixture 清單

```
backend/tests/fixtures/audio/
├── valid_16k_mono.wav        # 直通基準
├── valid_8k_mono.wav         # 觸發 resampling_warning
├── valid_48k_stereo.wav      # 觸發降採樣 + mono
├── valid_8bit.wav            # 觸發 8-bit 強制轉換
├── silence.wav               # 觸發 AUDIO_NO_SPEECH
├── corrupted.wav             # 觸發 AUDIO_RESAMPLE_FAILED
├── fake_extension.wav.zip    # 副檔名偽裝
└── empty.wav                 # 空檔案
```

### 5.8 Phase 1 不實作項目

| 項目 | 規格章節 | 順延 |
|------|---------|-----|
| ClearVoice 降噪 | 6.1 步驟 3 | Phase 2 |
| ForcedAligner 對齊 | 6.1 步驟 6 | Phase 2 |
| pyannote 語者分離 | 6.1 步驟 7 | Phase 2 |
| 後處理糾錯管線 | 6.1 步驟 8 | Phase 3 |
| VAD 能量閾值降級 | line 2563 | Phase 2 |

---

## 6. ASR 推理引擎整合與端點設計

### 6.1 vLLM 啟動載入

```python
class AsrEngineManager:
    _engine: AsyncLLMEngine | None = None
    _model_version: str | None = None

    @classmethod
    async def initialize(cls, settings: Settings) -> None:
        engine_args = AsyncEngineArgs(
            model=settings.ASR_MODEL_PATH,
            dtype="float16",
            gpu_memory_utilization=settings.VLLM_GPU_MEMORY_UTILIZATION,
            max_num_seqs=settings.MAX_INFERENCE_BATCH,
            max_model_len=settings.ASR_MAX_TOKENS,
        )
        cls._engine = AsyncLLMEngine.from_engine_args(engine_args)
        cls._model_version = compute_model_version(settings.ASR_MODEL_PATH)
        await audit_log("model.loaded", metadata={"model_version": cls._model_version})

    @classmethod
    async def shutdown(cls) -> None:
        if cls._engine is not None:
            await cls._engine.abort_all()
            cls._engine = None
        await audit_log("model.unloaded")

    @classmethod
    def get_engine(cls) -> AsyncLLMEngine:
        if cls._engine is None:
            raise AppException("ASR_ENGINE_UNAVAILABLE", http_status=503)
        return cls._engine

    @classmethod
    def model_version(cls) -> str:
        return cls._model_version or "unknown"
```

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    run_startup_checks(settings)
    FireRedVADService.load(Path(settings.VAD_MODEL_PATH))
    await AsrEngineManager.initialize(settings)
    yield
    await AsrEngineManager.shutdown()
```

`compute_model_version()` 來源優先序：模型目錄內的 `version.json` > `model.safetensors` SHA256 前 8 字元。

### 6.2 佇列抽象層

```python
class QueuePriority(StrEnum):
    REALTIME = "realtime"
    BATCH = "batch"

@dataclass
class AsrJob:
    job_id: str
    audio_file_id: int
    api_key_id: int
    options: TranscribeOptions
    enqueued_at: datetime

class QueueBackend(ABC):
    @abstractmethod
    async def enqueue(self, job: AsrJob, priority: QueuePriority) -> str: ...
    @abstractmethod
    async def dequeue(self) -> AsrJob: ...
    @abstractmethod
    async def cancel(self, job_id: str) -> bool: ...
    @abstractmethod
    async def status(self, job_id: str) -> dict: ...
    @abstractmethod
    def size(self, priority: QueuePriority | None = None) -> int: ...

class AsyncioQueueBackend(QueueBackend):
    def __init__(self, realtime_max: int, batch_max: int):
        self._realtime: asyncio.Queue[AsrJob] = asyncio.Queue(maxsize=realtime_max)
        self._batch: asyncio.Queue[AsrJob] = asyncio.Queue(maxsize=batch_max)
        # ...省略
```

Phase 1 僅 `BATCH` 通道使用；`REALTIME` 通道保留介面，Phase 2 配合 WS 啟用。

### 6.3 Phase 1 模式：同步 API + 內部 Queue

```
POST /api/v1/asr/transcribe
  ① 預處理（MIME / store / resample / VAD）
  ② 包裝為 AsrJob
  ③ queue.enqueue(job, BATCH)（滿載 → QUEUE_FULL）
  ④ 等待 future（asyncio.wait_for(future, timeout=ASR_REQUEST_TIMEOUT_SEC)）
  ⑤ Consumer task（背景 lifespan task）呼叫 Transcriber.run(job)
  ⑥ Consumer 完成設置 future result
  ⑦ HTTP 回傳完整 TranscribeData
```

### 6.4 Transcriber 編排

```python
class Transcriber:
    async def run(self, job: AsrJob) -> Transcription:
        audio = self.audio_repo.get(job.audio_file_id)
        if audio is None:
            raise AppException("NOT_FOUND")

        if audio.duration_sec > 20 * 60:
            raise AppException(
                "ASR_AUDIO_TOO_LONG", http_status=413,
                details={"limit_sec": 1200, "actual_sec": audio.duration_sec},
            )

        record = self.transcription_repo.create(
            file_name=audio.original_name,
            source="upload",
            duration_sec=audio.duration_sec,
            language=job.options.language,
            model_name="Qwen3-ASR-1.7B",
            model_version=self.model_version,
            status="processing",
        )
        self.audio_repo.set_transcription_id(audio.id, record.id)

        try:
            t0 = time.monotonic()
            result = await self.engine.generate(
                prompt=build_asr_prompt(audio.storage_path, job.options),
                sampling_params=SamplingParams(...),
            )
            duration = time.monotonic() - t0
        except CudaError as e:
            self.transcription_repo.update(record.id, status="failed", error_message=str(e))
            await audit_log("asr.cuda_error", metadata={"job_id": job.job_id})
            raise AppException("ASR_CUDA_ERROR", http_status=503)
        except Exception as e:
            self.transcription_repo.update(record.id, status="failed", error_message=str(e))
            raise AppException("ASR_INFERENCE_FAILED", http_status=500)

        parsed = parse_vllm_output(result)
        self.transcription_repo.update(
            record.id, status="completed",
            transcript_text=parsed.text,
            timestamps=parsed.timestamps if job.options.return_timestamps else None,
            processing_duration_sec=duration,
        )
        return self.transcription_repo.get(record.id)
```

### 6.5 端點 schema 與實作

**請求：**

```python
class TranscribeOptions(BaseModel):
    model: str | None = None
    language: str | None = None
    return_timestamps: bool = True
    diarization: bool | None = None         # Phase 1 接收但忽略，回 warning
    post_processing: bool | None = None
    denoise_enabled: bool | None = None
    nec_enabled: bool | None = None
    punctuation_enabled: bool | None = None
    hotword_group_ids: list[int] | None = None
    vad_enabled: bool = True
```

**回應：**

```python
class TranscribeData(BaseModel):
    transcription_id: int
    audio_file_id: int
    text: str
    timestamps: list[Timestamp] | None
    language: str | None
    duration_sec: float
    processing_duration_sec: float
    model_version: str
    resampling_warning: bool
    vad_segments_count: int
    warnings: list[str] = []
```

**路由：**

```python
@router.post("/transcribe", response_model=ResponseEnvelope[TranscribeData])
async def transcribe(
    file: UploadFile = File(...),
    options_json: str = Form("{}"),
    api_key: ApiKey = Depends(require_scope("asr:write")),
    db: Session = Depends(get_db),
):
    options = TranscribeOptions.model_validate_json(options_json)
    warnings = collect_unsupported_warnings(options)

    raw_bytes = await file.read()
    if len(raw_bytes) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise AppException("AUDIO_FILE_TOO_LARGE")

    verified_mime = verify_mime(raw_bytes)
    audio = await storage.store_upload(raw_bytes, ext_from_mime(verified_mime), api_key.id)
    resample = await resample_to_16k_mono(audio.storage_path)
    audio_repo.update_metadata(audio.id, resample)
    vad_segments = await FireRedVADService.detect_speech(resample.output_path)

    job = AsrJob(
        job_id=str(uuid4()),
        audio_file_id=audio.id,
        api_key_id=api_key.id,
        options=options,
        enqueued_at=datetime.now(UTC),
    )
    await queue.enqueue(job, QueuePriority.BATCH)
    transcription = await wait_for_job(job.job_id, timeout=settings.ASR_REQUEST_TIMEOUT_SEC)

    return ResponseEnvelope(
        success=True,
        data=TranscribeData(
            transcription_id=transcription.id,
            audio_file_id=audio.id,
            text=transcription.transcript_text,
            timestamps=transcription.timestamps,
            language=transcription.language,
            duration_sec=transcription.duration_sec,
            processing_duration_sec=transcription.processing_duration_sec,
            model_version=transcription.model_version,
            resampling_warning=resample.resampling_warning,
            vad_segments_count=len(vad_segments),
            warnings=warnings,
        ),
        error=None,
    )
```

### 6.6 雙模型交替策略對 Phase 1 的影響

| 規格要求 | Phase 1 處置 |
|---------|-------------|
| `transcriptions.model_version` 必填 | 啟動時計算，每筆寫入 |
| `POST /api/v1/asr/switch-model` 端點 | Phase 1 不實作，留 stub 501 |
| 雙模型槽位（active / standby） | Phase 1 僅 active |
| 任務綁定當時版本 | 寫入紀錄包含當前 `model_version` |

### 6.7 Phase 1 未實作的 ASR 相關端點

| 端點 | 順延 |
|------|-----|
| `GET /api/v1/asr/history` | Phase 2 |
| `GET /api/v1/asr/history/:id` | Phase 2 |
| `POST /api/v1/asr/download/:id` | Phase 2 |
| `GET /api/v1/asr/queue` | Phase 2 |
| `POST /api/v1/asr/queue/cancel/:id` | Phase 2 |
| `GET /api/v1/asr/models` | Phase 2 |
| `POST /api/v1/asr/switch-model` | Phase 2 |
| `POST /api/v1/asr/batch` | Phase 2 |
| `POST /api/v1/asr/upload/*` | Phase 2 |

---

## 7. 測試策略、CI 與環境變數

### 7.1 測試結構

```
backend/tests/
├── conftest.py
├── unit/
│   ├── test_security.py
│   ├── test_response_envelope.py
│   ├── test_settings.py
│   ├── test_tenant_repository.py
│   ├── test_mime.py
│   ├── test_resampler.py
│   ├── test_vad.py
│   ├── test_transcriber.py
│   └── test_queue.py
├── integration/
│   ├── test_alembic_roundtrip.py
│   ├── test_health_endpoints.py
│   ├── test_auth_flow.py
│   ├── test_audit_log_writes.py
│   ├── test_transcribe_endpoint.py
│   └── test_repositories.py
└── fixtures/
    ├── audio/
    └── factories.py
```

### 7.2 覆蓋率閾值

- 全域 ≥ 70%
- 熱點檔案 ≥ 90%：`core/security.py`、`repositories/base.py`、`services/audio/mime.py`、`services/asr/transcriber.py`、`middleware/error_handler.py`

### 7.3 標記策略

```python
[tool.pytest.ini_options]
markers = [
    "gpu: 需要真實 GPU 環境（CI 跳過）",
    "slow: 執行 > 5 秒",
    "phase2: Phase 2 才啟用的 placeholder 測試",
]
addopts = "-m 'not gpu and not phase2' --strict-markers"
```

### 7.4 PostgreSQL 依賴

選擇 `testcontainers-python`，每次 session 新建 container。連接 Phase 1 自訂的 `qwen-asr-postgres:test`（含 zhparser）。

### 7.5 CI 流程（GitHub Actions）

Phase 1 必過 job：
- `lint-type`：ruff check + ruff format --check + mypy
- `test`：pytest + 覆蓋率 ≥ 70%
- `migration-check`：Alembic upgrade → downgrade → upgrade round-trip
- `docker-build`：backend builder + runtime（CPU stage）
- `api-contract`：ResponseEnvelope schema 自動掃描

Phase 2+ 新增：`secret-scan`、`license-audit`、`e2e-playwright`、`vulnerability-scan`、`gpu-smoke`（手動觸發）。

### 7.6 Phase 1 環境變數白名單

**必填：** `API_KEY`、`DATABASE_URL`、`DB_PASSWORD`、`THIRD_PARTY_LICENSE_ACK`、`ENV`、`DEPLOYMENT_PROFILE`

**模型與 vLLM：** `ASR_MODEL`、`MODEL_CACHE_DIR`、`BACKEND_TYPE`、`VLLM_GPU_MEMORY_UTILIZATION`（Phase 1 預設 `0.5`，覆寫規格 `0.8`）、`GPU_DEVICE`、`MAX_INFERENCE_BATCH`、`ASR_MAX_TOKENS`（補充）、`ASR_REQUEST_TIMEOUT_SEC`（補充）、`ASR_AUDIO_MAX_DURATION_SEC`（補充）

**音檔處理：** `AUDIO_STORAGE_DIR`、`VAD_ENABLED`、`VAD_MODEL_PATH`（補充）、`MAX_UPLOAD_SIZE_MB`（Phase 1 預設 `100`，覆寫規格 `500`）、`MAX_DECODE_SIZE_MB`（補充）、`SUPPORTED_AUDIO_FORMATS`

**佇列：** `QUEUE_BATCH_MAX_SIZE`、`QUEUE_REJECT_BEHAVIOR`、`QUEUE_REALTIME_MAX_SIZE`（保留）

**可觀測性：** `LOG_LEVEL`、`LOG_FORMAT`（強制 `json`）

**安全與 CORS：** `CORS_ORIGINS`、`CORS_ALLOW_CREDENTIALS`、`OPENAPI_DOCS_ENABLED`、`OPENAPI_DOCS_REQUIRE_AUTH`

**補充變數（建議提 PR 寫入規格 10 節）：**

| 變數 | 預設值 | 用途 |
|------|--------|------|
| `ASR_MAX_TOKENS` | `4096` | vLLM `max_model_len` |
| `ASR_REQUEST_TIMEOUT_SEC` | `1200` | HTTP 等待 job 完成上限 |
| `ASR_AUDIO_MAX_DURATION_SEC` | `1200` | 單檔長度上限（對齊 20 分鐘） |
| `VAD_MODEL_PATH` | `/data/models/FireRedVAD/model.bin` | FireRedVAD 權重路徑 |
| `MAX_DECODE_SIZE_MB` | `500` | torchaudio 載入前硬性上限 |

### 7.7 啟動檢查清單

```python
def run_startup_checks(settings: Settings) -> None:
    if not settings.THIRD_PARTY_LICENSE_ACK:
        sys.exit("THIRD_PARTY_LICENSE_ACK 未設定為 true，依規格 26 節拒絕啟動")
    if settings.BACKEND_TYPE != "vllm":
        sys.exit(f"BACKEND_TYPE 必須為 'vllm'，目前為 '{settings.BACKEND_TYPE}'")
    if not settings.VAD_ENABLED:
        logger.warning("VAD_ENABLED=false 違反規格 6.1 推薦")
    asr_path = Path(settings.MODEL_CACHE_DIR) / settings.ASR_MODEL.replace("/", "_")
    if not asr_path.exists() and settings.ENV != "development":
        sys.exit(f"ASR 模型權重不存在：{asr_path}")
    audio_dir = Path(settings.AUDIO_STORAGE_DIR)
    audio_dir.mkdir(parents=True, exist_ok=True)
    if not os.access(audio_dir, os.W_OK):
        sys.exit(f"AUDIO_STORAGE_DIR 不可寫：{audio_dir}")
    test_db_connection(settings.DATABASE_URL)
    if settings.ENV == "production" and not settings.OPENAPI_DOCS_REQUIRE_AUTH:
        sys.exit("Production 模式必須 OPENAPI_DOCS_REQUIRE_AUTH=true")
```

### 7.8 Bootstrap admin 金鑰

```python
async def bootstrap_admin_key(db: Session, settings: Settings) -> None:
    count = db.query(ApiKey).filter(ApiKey.deleted_at.is_(None)).count()
    if count > 0:
        return
    if not settings.API_KEY:
        sys.exit("api_keys 表為空但未提供 API_KEY 環境變數")
    key = ApiKey(
        key_hash=argon2_hasher.hash(settings.API_KEY),
        lookup_prefix=lookup_prefix(settings.API_KEY),
        name="bootstrap-admin",
        description="啟動時自動建立的管理員金鑰",
        scopes=["admin"],
    )
    db.add(key)
    db.commit()
    await audit_log("auth.key_created", target_api_key_id=key.id, metadata={"reason": "bootstrap"})
```

### 7.9 Settings 載入優先序

```
process env > .env.local > .env > defaults
```

`.env.local` 已於 `.gitignore` 排除，作為開發者個人化覆蓋使用。

---

## 8. 完成標準（Phase 1 整體 Exit Criteria）

Phase 1 完成代表以下全部成立：

1. M1 → M2 → M3 → M4 全部 commit 已推送，並通過各自 DoD
2. CI 全部 job 綠燈（lint-type / test / migration-check / docker-build / api-contract）
3. 整體覆蓋率 ≥ 70%、熱點檔案 ≥ 90%
4. Linux + GPU 環境 `scripts/smoke_asr.sh` 用 1 分鐘音檔成功回傳逐字稿、`model_version`、`processing_duration_sec`
5. PHASE1-SPEC-01 規格瑕疵已透過 PR 修正規格書 5.9 + 19.1，或在 Phase 1 結束時提交修正 PR

完成後具備能力：

- 持有有效 Bearer Token 的客戶端，可以對 ≤ 20 分鐘的 16 kHz mono WAV / 8 kHz / 48 kHz / mp3 / m4a 等格式音檔發起 `POST /api/v1/asr/transcribe`，獲取逐字稿與時間戳
- 多租戶資料完全隔離（驗證通過）
- 系統重啟後 schema 完整、bootstrap 金鑰存在
- 所有錯誤路徑回傳統一 ResponseEnvelope 結構與附錄 A 錯誤碼

---

## 9. 後續 Phase 接口預留（不在 Phase 1 範圍）

Phase 2 啟動時可直接擴展的延伸點：

| 延伸點 | Phase 1 留下的 hook |
|--------|---------------------|
| Prometheus 指標 | `middleware/prometheus.py`（no-op） |
| OpenTelemetry tracing | `middleware/tracing.py`（no-op） |
| slowapi 限流 | `middleware/rate_limit.py`（no-op） |
| Idempotency-Key | `middleware/idempotency.py`（no-op） |
| Redis 佇列 | `QueueBackend` 抽象 + `RedisQueueBackend` 子類 |
| WS `/ws/quality` | `QUEUE_REALTIME` 通道、`AsrJob` 結構 |
| 雙模型切換 | `AsrEngineManager` 加 standby 槽位 |
| 分片上傳 | 加 `chunked_uploads` migration、`/api/v1/asr/upload/*` 路由 |
| Hotword 三層架構 | 加 `hotword_groups` / `hotwords` migration、`POST /transcribe` 接收 `hotword_group_ids` |
| 後處理糾錯管線 | `transcriptions.normalized_text` / `post_processing` 寫入 |
| 語者分離 | `transcriptions.speakers` 寫入 |
| Fine-tune | 加 `finetune_tasks` / `datasets` / `finetune_checkpoints` migration |

---

## 10. 規格瑕疵彙整（待 PR）

| 編號 | 規格章節 | 問題 | 補丁 |
|------|---------|------|------|
| PHASE1-SPEC-01 | 19.1（line 2602）+ 5.9 表格 | 「以 Argon2id 雜湊 token，查詢 `api_keys.key_hash`」實作不可行 | `api_keys` 加 `lookup_prefix VARCHAR(16) NOT NULL`，認證流程用 HMAC-SHA256 前綴查找 + Argon2id 最終 verify |
| PHASE1-SPEC-02 | 10 節環境變數表 | 缺 `ASR_MAX_TOKENS`、`ASR_REQUEST_TIMEOUT_SEC`、`ASR_AUDIO_MAX_DURATION_SEC`、`VAD_MODEL_PATH`、`MAX_DECODE_SIZE_MB` | 補入表格 |
