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
        cmake \
        libboost-system-dev \
        libboost-thread-dev \
        libboost-program-options-dev \
        libboost-test-dev \
        git \
    && rm -rf /var/lib/apt/lists/*

# ============================================================
# Stage 2: builder — Python 依賴編譯
# ============================================================
FROM deps AS builder

ARG INSTALL_GPU_DEPS=false
ARG INSTALL_AUDIO_DEPS=false

WORKDIR /build
COPY pyproject.toml ./
# pip install -e "." 需要 app/__init__.py 存在才能解析 package 邊界
COPY app/__init__.py app/__init__.py

# 建立隔離 venv 並升級基礎工具
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --upgrade pip wheel setuptools
ENV PATH="/opt/venv/bin:$PATH"

# 條件式安裝依賴：base → [audio]（M3 起）→ [gpu]（M4 起）→ flash-attn prebuilt wheel
# 使用正式安裝（非 editable）確保 site-packages 內含 app 套件，
# 不依賴 /build 目錄，Stage 3 runtime 可正確 import。
#
# flash-attn 用 prebuilt wheel 而非 pip extras 安裝，原因：
# 1. flash-attn setup.py 在 PEP 517 isolated build env 直接 import torch，但
#    pip 隔離環境此時 torch 尚未裝，故走 source build 必失敗。
# 2. base image python:3.12-slim-bookworm 無 nvcc / CUDA toolkit，即使先裝
#    torch 仍編譯失敗。
# 3. 走 prebuilt wheel 避開上述，且 ABI 三要素（cu12 / torch 2.9 / cp312 /
#    cxx11abiTRUE）需與容器內 torch 精準匹配——目前 qwen-asr[vllm] 0.0.6
#    透過 vllm==0.14.0 拉 torch 2.9.1+cu128，cxx11_abi=True，匹配下列 wheel。
# 4. 升級 torch / cu 版本時必須同步更新此 URL 與 SHA256，否則 ABI 失配會在
#    runtime 觸發 undefined symbol 或 segfault（無 Python 例外可 catch）。
# 5. --no-deps 防止 pip resolver 在 wheel METADATA 的 Requires-Dist 觸發二次
#    torch 解析（torch 已由 qwen-asr[vllm] 鎖定）。
RUN pip install "." \
    && if [ "$INSTALL_AUDIO_DEPS" = "true" ]; then pip install ".[audio]"; fi \
    && if [ "$INSTALL_GPU_DEPS" = "true" ]; then \
         pip install ".[gpu]" \
         && pip install --no-deps \
            "https://github.com/Dao-AILab/flash-attention/releases/download/v2.8.3/flash_attn-2.8.3%2Bcu12torch2.9cxx11abiTRUE-cp312-cp312-linux_x86_64.whl#sha256=4e2f9e39313266b1544b68138b15b91ee6221eccf14f7902b7c6620351340810"; \
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
        curl \
        tini \
        gcc \
        g++ \
        python3-dev \
    && rm -rf /var/lib/apt/lists/*

# 建立非 root 使用者
RUN groupadd --gid 10001 asr && useradd --uid 10001 --gid asr --shell /bin/bash --create-home asr

COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY --chown=asr:asr app /app/app
COPY --chown=asr:asr pyproject.toml /app/pyproject.toml
# 容器啟動時自動跑 alembic upgrade head —— migrations 失敗 → entrypoint exit 非零 →
# compose restart loop 暴露錯誤。alembic.ini sqlalchemy.url 為 placeholder，env.py
# 會以 DATABASE_URL 環境變數覆寫，無需 build 時注入連線字串。
COPY --chown=asr:asr alembic.ini /app/alembic.ini
COPY --chown=asr:asr alembic /app/alembic
COPY --chown=asr:asr --chmod=755 scripts/entrypoint.sh /app/entrypoint.sh

USER asr

EXPOSE 8000

# 健康檢查（M2 完成後 /health 端點存在）
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# tini 為 PID 1，entrypoint.sh 在跑完 `alembic upgrade head` 後 `exec "$@"` 把
# 控制權轉給 CMD（uvicorn），確保 SIGTERM 等信號正確 forward 到 worker。
ENTRYPOINT ["/usr/bin/tini", "--", "/app/entrypoint.sh"]
# workers=1 強制：規格 3.1、3.3.7、7.2 節要求
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
