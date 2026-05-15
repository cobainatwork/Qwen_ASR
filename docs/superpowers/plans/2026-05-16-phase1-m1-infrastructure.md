# Phase 1 / M1 — 基礎設施與容器化骨架 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立 Qwen3-ASR 後端的容器化骨架，讓 `docker compose up -d postgres` 能起動含 zhparser 擴充的 PostgreSQL 16，並讓 `docker compose build asr-backend` 通過三階段建構的 CPU 階段，作為後續 M2 後端骨架的工作基準。

**Architecture:** 雙服務 Docker Compose（postgres 自訂映像 + asr-backend 三階段映像）。Postgres 透過 `postgres:16-bookworm` 加裝 zhparser 中文全文檢索擴充。Backend 採三階段建構：`deps`（系統套件）→ `builder`（Python 依賴編譯）→ `runtime`（最終映像，GPU 環境執行）。所有 Python 應用碼留待 M2 撰寫，M1 僅建立 `backend/app/__init__.py` 占位以驗證 ruff / mypy 配置可運作。

**Tech Stack:** Docker Compose、PostgreSQL 16（zhparser）、Python 3.12、ruff、mypy、pytest（配置就緒，實際測試於 M2 起）。

**對應設計文件：** `docs/superpowers/specs/2026-05-16-phase1-implementation-design.md` 第 1.1、2.2 章節。

---

## File Structure

| 路徑 | 動作 | 責任 |
|------|------|------|
| `backend/pyproject.toml` | Create | Python 套件、ruff / mypy / pytest 配置 |
| `backend/app/__init__.py` | Create | 占位空檔案，讓 mypy / ruff 有可掃描標的 |
| `backend/Dockerfile` | Create | 三階段建構腳本 |
| `backend/.dockerignore` | Create | 排除 venv、cache、__pycache__ 等 |
| `postgres/Dockerfile` | Create | PostgreSQL 16 + zhparser 自訂映像 |
| `postgres/init.sql` | Create | 啟用 zhparser extension、定義 chinese text search config |
| `docker-compose.yml` | Create | postgres + asr-backend 服務組成 |
| `.env.example` | Create | Phase 1 環境變數樣板 |

---

## Task 1.1：建立 `backend/pyproject.toml` 與 ruff / mypy / pytest 配置

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/app/__init__.py`

- [ ] **Step 1：建立 backend 目錄**

```bash
mkdir backend
mkdir backend/app
```

- [ ] **Step 2：建立 `backend/app/__init__.py`（空檔案，僅作占位）**

```python
```

（檔案內容為空。git 不追蹤空目錄，需檔案存在才能在後續 task 加入子模組。）

- [ ] **Step 3：撰寫 `backend/pyproject.toml`**

```toml
[build-system]
requires = ["hatchling>=1.24"]
build-backend = "hatchling.build"

[project]
name = "qwen-asr-backend"
version = "0.1.0"
description = "Qwen3-ASR 離線語音辨識平台 — 後端"
requires-python = ">=3.12"
readme = { content-type = "text/markdown", text = "Backend for Qwen3-ASR platform. See docs/superpowers/specs/." }

dependencies = [
  # 核心框架（M2 起使用，先列依賴避免 M2 重複改動）
  "fastapi>=0.115.0",
  "uvicorn[standard]>=0.32.0",
  "pydantic>=2.9.0",
  "pydantic-settings>=2.6.0",
  "sqlalchemy>=2.0.35",
  "alembic>=1.14.0",
  "psycopg[binary]>=3.2.0",
  "argon2-cffi>=23.1.0",
  "structlog>=24.4.0",
  "python-multipart>=0.0.17",
  # 預處理依賴（M3 起使用）
  "python-magic>=0.4.27",
  "torch>=2.4.0",
  "torchaudio>=2.4.0",
  "soxr>=0.5.0",
  "soundfile>=0.12.1",
  "numpy>=1.26.0",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.3.0",
  "pytest-asyncio>=0.24.0",
  "pytest-cov>=5.0.0",
  "httpx>=0.27.0",
  "testcontainers[postgres]>=4.8.0",
  "factory-boy>=3.3.1",
  "ruff>=0.7.0",
  "mypy>=1.13.0",
]
gpu = [
  # vLLM 與 GPU 推理（M4 起使用）；CPU CI 不安裝
  "vllm>=0.6.0",
]

[tool.hatch.build.targets.wheel]
packages = ["app"]

# ---------------- Ruff ----------------
[tool.ruff]
line-length = 100
target-version = "py312"
src = ["app", "tests"]

[tool.ruff.lint]
select = [
  "E", "W",      # pycodestyle
  "F",            # pyflakes
  "I",            # isort
  "B",            # flake8-bugbear
  "UP",           # pyupgrade
  "ASYNC",        # flake8-async
  "S",            # flake8-bandit
  "RUF",          # ruff-specific
]
ignore = [
  "S101",  # pytest 內使用 assert
]

[tool.ruff.lint.per-file-ignores]
"tests/**/*.py" = ["S105", "S106", "S311"]  # 測試中允許 hardcoded password、隨機

# ---------------- mypy ----------------
[tool.mypy]
python_version = "3.12"
strict = true
warn_unused_ignores = true
warn_redundant_casts = true
warn_return_any = true
files = ["app"]

[[tool.mypy.overrides]]
module = ["torchaudio.*", "soxr.*", "soundfile.*", "magic.*", "vllm.*"]
ignore_missing_imports = true

# ---------------- pytest ----------------
[tool.pytest.ini_options]
minversion = "8.0"
asyncio_mode = "auto"
testpaths = ["tests"]
addopts = "-m 'not gpu and not phase2' --strict-markers -ra"
markers = [
  "gpu: 需要真實 GPU 環境（CI 跳過）",
  "slow: 執行 > 5 秒",
  "phase2: Phase 2 才啟用的 placeholder 測試",
]

[tool.coverage.run]
source = ["app"]
branch = true

[tool.coverage.report]
fail_under = 70
show_missing = true
skip_covered = false
exclude_lines = [
  "pragma: no cover",
  "raise NotImplementedError",
  "if TYPE_CHECKING:",
]
```

- [ ] **Step 4：在本機建立 Python 虛擬環境並安裝**

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate     # Windows
# 或 source .venv/bin/activate  # Linux
pip install -e ".[dev]"
```

預期：安裝成功，無錯誤。

- [ ] **Step 5：執行 `ruff check`**

```bash
cd backend
ruff check .
```

預期輸出：`All checks passed!`（app/__init__.py 為空，無檔案需檢查）。

- [ ] **Step 6：執行 `mypy app`**

```bash
cd backend
mypy app
```

預期輸出：`Success: no issues found in 1 source file`。

- [ ] **Step 7：執行 `pytest`（測試目錄尚不存在）**

```bash
cd backend
pytest
```

預期輸出：`no tests ran`（exit code 5；CI 後續需處理此狀態）。

- [ ] **Step 8：Commit**

```bash
git add backend/pyproject.toml backend/app/__init__.py
git commit -m "chore(backend): 建立 pyproject.toml 與 ruff / mypy / pytest 配置"
```

---

## Task 1.2：建立 `backend/Dockerfile`（三階段建構）

**Files:**
- Create: `backend/Dockerfile`

- [ ] **Step 1：撰寫 `backend/Dockerfile`**

```dockerfile
# syntax=docker/dockerfile:1.7

# ============================================================
# Stage 1: deps — 系統套件層（含 libmagic、ffmpeg、build-essential）
# ============================================================
FROM python:3.12-slim-bookworm AS deps

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        ca-certificates \
        libmagic1 \
        ffmpeg \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# ============================================================
# Stage 2: builder — Python 依賴編譯
# ============================================================
FROM deps AS builder

ARG INSTALL_GPU_DEPS=false

WORKDIR /build
COPY pyproject.toml ./
COPY app/__init__.py app/__init__.py

# 安裝 wheel 並建立隔離 venv
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN pip install --upgrade pip wheel setuptools

# 條件式安裝 GPU 依賴
RUN if [ "$INSTALL_GPU_DEPS" = "true" ]; then \
        pip install -e ".[gpu]"; \
    else \
        pip install -e "."; \
    fi

# ============================================================
# Stage 3: runtime — 最終映像
# ============================================================
FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

RUN apt-get update && apt-get install -y --no-install-recommends \
        libmagic1 \
        ffmpeg \
        libpq5 \
        ca-certificates \
        tini \
    && rm -rf /var/lib/apt/lists/*

# 建立非 root 使用者
RUN groupadd --gid 10001 asr && useradd --uid 10001 --gid asr --shell /bin/bash --create-home asr

COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY --chown=asr:asr app /app/app
COPY --chown=asr:asr pyproject.toml /app/pyproject.toml

USER asr

EXPOSE 8000

# 健康檢查（M2 完成後 /health 端點存在）
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
# workers=1 強制：規格 3.1、3.3.7、7.2 節要求
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
```

- [ ] **Step 2：建構 builder 階段（驗證系統套件與依賴安裝）**

```bash
cd D:\Qwen_asr
docker build --target builder -t qwen-asr-backend:builder backend/
```

預期：建構成功，最後一行為 `naming to docker.io/library/qwen-asr-backend:builder`。

- [ ] **Step 3：建構 runtime 階段（CPU only，不含 vLLM）**

```bash
docker build --target runtime -t qwen-asr-backend:test --build-arg INSTALL_GPU_DEPS=false backend/
```

預期：建構成功。

- [ ] **Step 4：檢查映像大小（runtime 階段應顯著小於 builder）**

```bash
docker images qwen-asr-backend
```

預期：`qwen-asr-backend:test`（runtime）約 1.0–1.5 GB；builder 階段約 2.5–4 GB。

- [ ] **Step 5：驗證映像可啟動（雖然 M2 才有 app.main:app，這步預期失敗但容器須啟得了）**

```bash
docker run --rm qwen-asr-backend:test python -c "import sys; print(sys.version)"
```

預期：印出 Python 3.12.x 版本資訊。

- [ ] **Step 6：Commit**

```bash
git add backend/Dockerfile
git commit -m "chore(backend): 加入三階段 Dockerfile（deps / builder / runtime）"
```

---

## Task 1.3：建立 `postgres/Dockerfile` 與 zhparser init.sql

**Files:**
- Create: `postgres/Dockerfile`
- Create: `postgres/init.sql`

- [ ] **Step 1：建立 postgres 目錄與 Dockerfile**

```bash
mkdir postgres
```

撰寫 `postgres/Dockerfile`：

```dockerfile
# syntax=docker/dockerfile:1.7
FROM postgres:16-bookworm

ENV DEBIAN_FRONTEND=noninteractive

# 安裝建構工具與 zhparser 編譯依賴
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        postgresql-server-dev-16 \
        libscws3 \
        libscws-dev \
        git \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 編譯 zhparser
RUN git clone --depth 1 https://github.com/amutu/zhparser.git /tmp/zhparser \
    && cd /tmp/zhparser \
    && make \
    && make install \
    && cd / \
    && rm -rf /tmp/zhparser

# 移除建構工具（縮小映像）
RUN apt-get purge -y --auto-remove build-essential postgresql-server-dev-16 git \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/*

# 初始化腳本（容器首次啟動執行）
COPY init.sql /docker-entrypoint-initdb.d/init.sql
```

- [ ] **Step 2：撰寫 `postgres/init.sql`**

```sql
-- 啟用 zhparser 擴充
CREATE EXTENSION IF NOT EXISTS zhparser;

-- 建立中文文本搜尋設定
CREATE TEXT SEARCH CONFIGURATION chinese (PARSER = zhparser);

-- 加入詞性映射（依規格書 11.2）
ALTER TEXT SEARCH CONFIGURATION chinese
    ADD MAPPING FOR n,v,a,i,e,l WITH simple;
```

- [ ] **Step 3：建構 postgres 映像**

```bash
cd D:\Qwen_asr
docker build -t qwen-asr-postgres:test postgres/
```

預期：建構成功。

- [ ] **Step 4：啟動容器並驗證 zhparser 可載入**

```bash
docker run --rm -d --name pg-test -e POSTGRES_PASSWORD=test qwen-asr-postgres:test
```

等待 10 秒讓 init.sql 執行完畢：

```bash
# Windows PowerShell
Start-Sleep -Seconds 10
# 或 Linux
sleep 10
```

- [ ] **Step 5：透過 docker exec 確認 zhparser 已啟用**

```bash
docker exec pg-test psql -U postgres -c "\dx" | findstr zhparser
# Linux: docker exec pg-test psql -U postgres -c "\dx" | grep zhparser
```

預期輸出：`zhparser    | 2.x   | public  | a parser for full-text search of Chinese`

- [ ] **Step 6：確認 chinese text search config 存在**

```bash
docker exec pg-test psql -U postgres -c "\dF chinese"
```

預期輸出：列出 `chinese` text search configuration。

- [ ] **Step 7：實際測試中文分詞**

```bash
docker exec pg-test psql -U postgres -c "SELECT to_tsvector('chinese', '今天天氣很好我們去公園散步');"
```

預期：輸出包含「今天」、「天氣」、「公園」、「散步」等分詞結果。

- [ ] **Step 8：清理測試容器**

```bash
docker stop pg-test
```

- [ ] **Step 9：Commit**

```bash
git add postgres/Dockerfile postgres/init.sql
git commit -m "chore(postgres): 加入 PostgreSQL 16 + zhparser 自訂映像"
```

---

## Task 1.4：建立 `.dockerignore`

**Files:**
- Create: `backend/.dockerignore`

- [ ] **Step 1：撰寫 `backend/.dockerignore`**

```gitignore
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
.venv/
venv/
env/

# 測試與快取
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage
.coverage.*
htmlcov/
coverage.xml
.hypothesis/

# 套件建構
*.egg-info/
*.egg
build/
dist/
wheels/

# IDE 與 OS
.vscode/
.idea/
.DS_Store
Thumbs.db
*.swp

# Git
.git/
.gitignore
.gitattributes

# 本地環境
.env
.env.local
.env.*.local

# 文件（不需進映像）
*.md
docs/
tests/
fixtures/

# Docker 本身
Dockerfile
.dockerignore

# 模型權重（必須透過 volume 掛載）
models/
checkpoints/
*.pt
*.pth
*.safetensors
*.bin
```

- [ ] **Step 2：重新建構 builder 階段，驗證 .dockerignore 生效**

```bash
docker build --target builder -t qwen-asr-backend:builder backend/ 2>&1 | findstr /R "transferring context"
# Linux: docker build --target builder -t qwen-asr-backend:builder backend/ 2>&1 | grep "transferring context"
```

預期：context size 顯著小於 Task 1.2 的初次建構（無 .venv、無 cache）。

- [ ] **Step 3：Commit**

```bash
git add backend/.dockerignore
git commit -m "chore(backend): 加入 .dockerignore 排除虛擬環境與快取"
```

---

## Task 1.5：建立 `docker-compose.yml`

**Files:**
- Create: `docker-compose.yml`

- [ ] **Step 1：撰寫 `docker-compose.yml`**

```yaml
services:
  postgres:
    build:
      context: ./postgres
      dockerfile: Dockerfile
    image: qwen-asr-postgres:dev
    container_name: qwen-asr-postgres
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-qwasr}
      POSTGRES_PASSWORD: ${DB_PASSWORD:?DB_PASSWORD is required}
      POSTGRES_DB: ${POSTGRES_DB:-qwen_asr}
      PGDATA: /var/lib/postgresql/data/pgdata
    ports:
      - "${POSTGRES_PORT:-5432}:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-qwasr} -d ${POSTGRES_DB:-qwen_asr}"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s

  asr-backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
      target: runtime
      args:
        INSTALL_GPU_DEPS: ${INSTALL_GPU_DEPS:-false}
    image: qwen-asr-backend:dev
    container_name: qwen-asr-backend
    environment:
      # 必填
      API_KEY: ${API_KEY:?API_KEY is required}
      DATABASE_URL: ${DATABASE_URL:-postgresql+psycopg://qwasr:${DB_PASSWORD}@postgres:5432/qwen_asr}
      DB_PASSWORD: ${DB_PASSWORD}
      THIRD_PARTY_LICENSE_ACK: ${THIRD_PARTY_LICENSE_ACK:?must be true to start}
      ENV: ${ENV:-development}
      DEPLOYMENT_PROFILE: ${DEPLOYMENT_PROFILE:-client}
      # 模型與 vLLM
      ASR_MODEL: ${ASR_MODEL:-Qwen/Qwen3-ASR-1.7B}
      MODEL_CACHE_DIR: /data/models
      BACKEND_TYPE: vllm
      VLLM_GPU_MEMORY_UTILIZATION: ${VLLM_GPU_MEMORY_UTILIZATION:-0.5}
      GPU_DEVICE: ${GPU_DEVICE:-cuda:0}
      MAX_INFERENCE_BATCH: ${MAX_INFERENCE_BATCH:-32}
      ASR_MAX_TOKENS: ${ASR_MAX_TOKENS:-4096}
      ASR_REQUEST_TIMEOUT_SEC: ${ASR_REQUEST_TIMEOUT_SEC:-1200}
      ASR_AUDIO_MAX_DURATION_SEC: ${ASR_AUDIO_MAX_DURATION_SEC:-1200}
      # 音檔處理
      AUDIO_STORAGE_DIR: /data/audio
      VAD_ENABLED: ${VAD_ENABLED:-true}
      VAD_MODEL_PATH: /data/models/FireRedVAD/model.bin
      MAX_UPLOAD_SIZE_MB: ${MAX_UPLOAD_SIZE_MB:-100}
      MAX_DECODE_SIZE_MB: ${MAX_DECODE_SIZE_MB:-500}
      SUPPORTED_AUDIO_FORMATS: ${SUPPORTED_AUDIO_FORMATS:-wav,mp3,mp4,flac,aac,ogg,m4a}
      # 佇列
      QUEUE_BATCH_MAX_SIZE: ${QUEUE_BATCH_MAX_SIZE:-20}
      QUEUE_REALTIME_MAX_SIZE: ${QUEUE_REALTIME_MAX_SIZE:-50}
      QUEUE_REJECT_BEHAVIOR: ${QUEUE_REJECT_BEHAVIOR:-reject}
      # 可觀測性
      LOG_LEVEL: ${LOG_LEVEL:-INFO}
      LOG_FORMAT: ${LOG_FORMAT:-json}
      # 安全與 CORS
      CORS_ORIGINS: ${CORS_ORIGINS:-http://localhost:3000}
      CORS_ALLOW_CREDENTIALS: ${CORS_ALLOW_CREDENTIALS:-false}
      OPENAPI_DOCS_ENABLED: ${OPENAPI_DOCS_ENABLED:-true}
      OPENAPI_DOCS_REQUIRE_AUTH: ${OPENAPI_DOCS_REQUIRE_AUTH:-false}
    ports:
      - "${BACKEND_PORT:-8000}:8000"
    volumes:
      - ${MODEL_CACHE_DIR_HOST:-./.data/models}:/data/models
      - ${AUDIO_STORAGE_DIR_HOST:-./.data/audio}:/data/audio
    depends_on:
      postgres:
        condition: service_healthy
    restart: unless-stopped
    # GPU runtime（部署環境取消註解；M1 不啟用）
    # deploy:
    #   resources:
    #     reservations:
    #       devices:
    #         - driver: nvidia
    #           count: 1
    #           capabilities: [gpu]

volumes:
  pgdata:
    name: qwen-asr-pgdata
```

- [ ] **Step 2：驗證 docker-compose.yml 語法**

```bash
cd D:\Qwen_asr
# 建立暫時 .env 供 ${...} 解析
@"
API_KEY=dev-bootstrap-key
DB_PASSWORD=devpass
THIRD_PARTY_LICENSE_ACK=true
"@ | Out-File -Encoding utf8 .env

docker compose config
```

預期：輸出展開後的完整 yml，無語法錯誤。

- [ ] **Step 3：建構兩個 service（不啟動）**

```bash
docker compose build
```

預期：postgres 與 asr-backend 兩個 image 都建構成功。

- [ ] **Step 4：啟動 postgres，驗證健康檢查**

```bash
docker compose up -d postgres
Start-Sleep -Seconds 15  # Windows; Linux: sleep 15
docker compose ps postgres
```

預期：`STATUS` 欄位顯示 `Up (healthy)`。

- [ ] **Step 5：透過 docker compose exec 連線並驗證 zhparser**

```bash
docker compose exec postgres psql -U qwasr -d qwen_asr -c "\dx"
```

預期：列出 zhparser extension。

- [ ] **Step 6：拆除環境**

```bash
docker compose down
Remove-Item .env  # Windows; Linux: rm .env
```

- [ ] **Step 7：Commit**

```bash
git add docker-compose.yml
git commit -m "chore: 加入 docker-compose.yml（postgres + asr-backend 服務組成）"
```

---

## Task 1.6：建立 `.env.example`

**Files:**
- Create: `.env.example`

- [ ] **Step 1：撰寫 `.env.example`**

```bash
# ============================================================
# Qwen3-ASR Phase 1 環境變數樣板
# 使用方式：cp .env.example .env，並依需要修改值
# ============================================================

# ----- 必填 -----
# API 認證金鑰（建議使用 32+ 字元高熵字串）
API_KEY=please-change-me-to-strong-token

# PostgreSQL 連線資訊
DB_PASSWORD=please-change-me
DATABASE_URL=postgresql+psycopg://qwasr:please-change-me@postgres:5432/qwen_asr
POSTGRES_USER=qwasr
POSTGRES_DB=qwen_asr
POSTGRES_PORT=5432

# 第三方授權確認（依規格 26 節，未設 true 將拒絕啟動）
THIRD_PARTY_LICENSE_ACK=true

# 部署環境
ENV=development
DEPLOYMENT_PROFILE=client

# ----- 模型與 vLLM -----
ASR_MODEL=Qwen/Qwen3-ASR-1.7B
VLLM_GPU_MEMORY_UTILIZATION=0.5
GPU_DEVICE=cuda:0
MAX_INFERENCE_BATCH=32
ASR_MAX_TOKENS=4096
ASR_REQUEST_TIMEOUT_SEC=1200
ASR_AUDIO_MAX_DURATION_SEC=1200

# 是否在容器內安裝 GPU 依賴（vLLM）
# CI 與本地開發設為 false；部署到 GPU 主機設為 true
INSTALL_GPU_DEPS=false

# 模型權重與音檔的 host volume 掛載點
MODEL_CACHE_DIR_HOST=./.data/models
AUDIO_STORAGE_DIR_HOST=./.data/audio

# ----- 音檔處理 -----
VAD_ENABLED=true
MAX_UPLOAD_SIZE_MB=100
MAX_DECODE_SIZE_MB=500
SUPPORTED_AUDIO_FORMATS=wav,mp3,mp4,flac,aac,ogg,m4a

# ----- 佇列 -----
QUEUE_BATCH_MAX_SIZE=20
QUEUE_REALTIME_MAX_SIZE=50
QUEUE_REJECT_BEHAVIOR=reject

# ----- 可觀測性 -----
LOG_LEVEL=INFO
LOG_FORMAT=json

# ----- 安全與 CORS -----
CORS_ORIGINS=http://localhost:3000
CORS_ALLOW_CREDENTIALS=false
OPENAPI_DOCS_ENABLED=true
OPENAPI_DOCS_REQUIRE_AUTH=false

# ----- 服務 port -----
BACKEND_PORT=8000
```

- [ ] **Step 2：複製為實際 `.env` 並驗證 docker compose 可解析**

```bash
cd D:\Qwen_asr
Copy-Item .env.example .env  # Windows; Linux: cp .env.example .env
docker compose config | findstr "API_KEY"
# Linux: docker compose config | grep "API_KEY"
```

預期：輸出 `API_KEY: please-change-me-to-strong-token` 等展開值。

- [ ] **Step 3：再次清理（保留 .env.example，但 .env 不進版控）**

```bash
Remove-Item .env  # Windows; Linux: rm .env
```

確認 `.gitignore` 已包含 `.env`（前一次 commit 已加入），驗證：

```bash
git check-ignore -v .env
```

預期輸出：`.gitignore:11:.env  .env`

- [ ] **Step 4：Commit**

```bash
git add .env.example
git commit -m "chore: 加入 .env.example 環境變數樣板"
```

---

## Task 1.7：M1 整合驗收

**Files:**（無新檔案，純執行）

- [ ] **Step 1：建立實際 `.env` 並啟動 postgres**

```bash
cd D:\Qwen_asr
Copy-Item .env.example .env  # Windows
# 修改 API_KEY 與 DB_PASSWORD 為較強的值（可使用 openssl 或 PowerShell）
docker compose up -d postgres
Start-Sleep -Seconds 20  # Windows
```

- [ ] **Step 2：驗證 postgres 健康狀態為 healthy**

```bash
docker compose ps postgres
```

預期：`STATUS` 為 `Up X seconds (healthy)`。

- [ ] **Step 3：驗證 zhparser 與 chinese text search 設定可用**

```bash
docker compose exec postgres psql -U qwasr -d qwen_asr -c "\dx" | findstr zhparser
docker compose exec postgres psql -U qwasr -d qwen_asr -c "SELECT to_tsvector('chinese', '繁體中文全文檢索測試');"
```

預期：兩個指令都成功，第二個輸出包含分詞 token。

- [ ] **Step 4：建構 asr-backend 映像（CPU 階段）**

```bash
docker compose build asr-backend
```

預期：建構成功。

- [ ] **Step 5：在容器內驗證 Python 環境**

```bash
docker compose run --rm asr-backend python -c "import fastapi, sqlalchemy, alembic, structlog, magic, torch, torchaudio; print('all imports OK')"
```

預期：印出 `all imports OK`。

> 註：torch / torchaudio CPU 版本檔案較大，第一次建構可能需要 5–10 分鐘下載。

- [ ] **Step 6：清理測試環境**

```bash
docker compose down -v   # -v 同時清除 pgdata volume
Remove-Item .env  # Windows
```

- [ ] **Step 7：建立 M1 驗收紀錄（不 commit，僅本機留檔協助 review）**

```bash
@"
M1 驗收 - $(Get-Date -Format yyyy-MM-dd)

[x] docker compose up -d postgres 啟動成功，healthy
[x] zhparser extension 載入並可分詞
[x] docker compose build asr-backend 通過
[x] 容器內 Python 依賴可正常 import
[x] .env.example 包含 Phase 1 所有變數
[x] 工作目錄拆除後乾淨

PR：尚未建立
"@ > .m1-verification.txt
```

> 此檔案為個人筆記，已被 `.gitignore` 中的 `*.txt` 模式（如未涵蓋則手動 ignore）。實作時若沒有則加 `.m1-verification.txt` 到 `.gitignore`。

- [ ] **Step 8：M1 完成標記（無 commit；直接推送至 origin/main）**

```bash
git log --oneline | Select-Object -First 8   # Windows; Linux: git log --oneline | head -8
git push origin main
```

預期：log 包含 Task 1.1–1.6 的 6 個 commit，皆已推送。

---

## Self-Review

**1. Spec coverage（對照設計文件第 1、2 段）：**

| 設計文件章節 | 對應 Task | 覆蓋狀態 |
|--------------|-----------|---------|
| 1.1 Docker Compose 服務組成 | 1.3、1.5、1.7 | 涵蓋 |
| 1.2 Backend 目錄骨架（M1 限 backend/、postgres/、配置檔） | 1.1、1.4 | 涵蓋（app/ 內細節留待 M2） |
| 1.3 設計原則對應 — `Dockerfile` CMD 固定 workers=1 | 1.2 | 涵蓋 |
| 2.2 M1 工作項目 | 1.1–1.7 | 全部涵蓋 |
| 2.2 M1 DoD 條件 1–5 | 1.7 Step 1–6 | 全部驗證 |

**2. Placeholder scan：** 已搜尋 `TBD`、`TODO`、`implement later`、`fill in details`、`add appropriate error handling`、`similar to Task N` 等紅旗，無命中。所有 code block 為實際可執行內容。

**3. Type consistency：** Task 1.1 定義依賴版本（fastapi>=0.115、sqlalchemy>=2.0.35 等），Task 1.2 Dockerfile 安裝同一 pyproject.toml，無版本衝突。Task 1.5 docker-compose 引用的環境變數（`API_KEY`、`DATABASE_URL` 等）與 Task 1.6 .env.example 完整對齊。

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-16-phase1-m1-infrastructure.md`. Two execution options:

**1. Subagent-Driven（推薦）** — 每個 Task 分派一個全新 subagent 執行，主對話進行兩階段審查（task 完成 → review → 下一 task）。隔離快、回滾簡單，適合此類有明確 DoD 的基礎設施任務。

**2. Inline Execution** — 在當前 session 內以批次方式跑完所有 Task，每完成 1–2 個 task 設一個 checkpoint 給使用者審查。

**M2 / M3 / M4 plan 待 M1 完成後再撰寫。** 也可一次寫齊 4 份 plan 後再執行（會延後 M1 啟動但避免設計漂移風險）。

請選擇執行策略，或指示先一次寫齊 M2–M4 plan 再執行。
