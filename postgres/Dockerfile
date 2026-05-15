# syntax=docker/dockerfile:1.7
FROM postgres:16-bookworm

ENV DEBIAN_FRONTEND=noninteractive

# 安裝建構工具與編譯依賴（libscws 不在 Debian Bookworm apt 倉庫，需從原始碼編譯）
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        postgresql-server-dev-16 \
        autoconf \
        automake \
        libtool \
        git \
        ca-certificates \
        wget \
    && rm -rf /var/lib/apt/lists/*

# 編譯安裝 SCWS（zhparser 的分詞引擎依賴）
# GitHub archive 只含 configure.ac，需先執行 autoreconf 產生 configure
RUN wget -qO /tmp/scws.tar.gz \
        https://github.com/hightman/scws/archive/refs/tags/1.2.3.tar.gz \
    && tar -xzf /tmp/scws.tar.gz -C /tmp \
    && cd /tmp/scws-1.2.3 \
    && autoreconf -fiv \
    && ./configure --prefix=/usr/local \
    && make install \
    && ldconfig \
    && cd / \
    && rm -rf /tmp/scws-1.2.3 /tmp/scws.tar.gz

# 編譯 zhparser
RUN git clone --depth 1 --branch v2.3 https://github.com/amutu/zhparser.git /tmp/zhparser \
    && cd /tmp/zhparser \
    && make \
    && make install \
    && cd / \
    && rm -rf /tmp/zhparser

# 移除建構工具（縮小映像）
RUN apt-get purge -y --auto-remove build-essential postgresql-server-dev-16 autoconf automake libtool git wget \
    && rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/*

# 初始化腳本（容器首次啟動執行）
COPY init.sql /docker-entrypoint-initdb.d/init.sql
