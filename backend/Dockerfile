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
