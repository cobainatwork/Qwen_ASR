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
ARG INSTALL_AUDIO_DEPS=false

WORKDIR /build
COPY pyproject.toml ./
# pip install -e "." 需要 app/__init__.py 存在才能解析 package 邊界
COPY app/__init__.py app/__init__.py

# 建立隔離 venv 並升級基礎工具
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --upgrade pip wheel setuptools
ENV PATH="/opt/venv/bin:$PATH"

# 條件式安裝依賴：base → [audio]（M3 起）→ [gpu]（M4 起）
# 使用正式安裝（非 editable）確保 site-packages 內含 app 套件，
# 不依賴 /build 目錄，Stage 3 runtime 可正確 import。
RUN pip install "." \
    && if [ "$INSTALL_AUDIO_DEPS" = "true" ]; then pip install ".[audio]"; fi \
    && if [ "$INSTALL_GPU_DEPS" = "true" ]; then pip install ".[gpu]"; fi

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
