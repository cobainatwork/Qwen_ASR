# syntax=docker/dockerfile:1.7

# ============================================================
# Stage 1: builder — 編譯 SCWS + zhparser，產物隨後丟棄
# ============================================================
FROM postgres:16-bookworm AS builder

ENV DEBIAN_FRONTEND=noninteractive

# 編譯依賴僅存在於 builder stage，不污染 runtime image
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

# 編譯 SCWS 1.2.3（zhparser 的中文分詞引擎依賴）
# GitHub archive 只含 configure.ac，需先 autoreconf 產生 configure
RUN wget -qO /tmp/scws.tar.gz \
        https://github.com/hightman/scws/archive/refs/tags/1.2.3.tar.gz \
    && tar -xzf /tmp/scws.tar.gz -C /tmp \
    && cd /tmp/scws-1.2.3 \
    && autoreconf -fiv \
    && ./configure --prefix=/usr/local \
    && make install \
    && ldconfig

# 編譯 zhparser v2.3（pin 版本避免 upstream 漂移）
RUN git clone --depth 1 --branch v2.3 https://github.com/amutu/zhparser.git /tmp/zhparser \
    && cd /tmp/zhparser \
    && make \
    && make install

# ============================================================
# Stage 2: runtime — 乾淨 postgres:16-bookworm + 從 builder 拷入產物
# ============================================================
FROM postgres:16-bookworm AS runtime

# SCWS 共享函式庫 + 規則檔
# libscws.so* 只依賴 libc + libm（postgres base 已含），無額外 apt 依賴。
# 直接 COPY glob `libscws.so*` 會把 symlink (libscws.so / libscws.so.1) 解引用
# 為三個一樣的實體檔，浪費 ~300 KB 並觸發 ldconfig "not a symbolic link" warning。
# 拷實體檔 + 在 runtime 重建 symlink 保持原 libtool 期望的鏈結。
COPY --from=builder /usr/local/lib/libscws.so.1.1.0 /usr/local/lib/libscws.so.1.1.0
COPY --from=builder /usr/local/etc/rules*.ini /usr/local/etc/
RUN cd /usr/local/lib \
    && ln -s libscws.so.1.1.0 libscws.so.1 \
    && ln -s libscws.so.1.1.0 libscws.so

# zhparser PostgreSQL extension
COPY --from=builder /usr/lib/postgresql/16/lib/zhparser.so /usr/lib/postgresql/16/lib/zhparser.so
COPY --from=builder /usr/lib/postgresql/16/lib/bitcode/zhparser/ /usr/lib/postgresql/16/lib/bitcode/zhparser/
COPY --from=builder /usr/lib/postgresql/16/lib/bitcode/zhparser.index.bc /usr/lib/postgresql/16/lib/bitcode/zhparser.index.bc
COPY --from=builder /usr/share/postgresql/16/extension/zhparser.control /usr/share/postgresql/16/extension/
COPY --from=builder /usr/share/postgresql/16/extension/zhparser--*.sql /usr/share/postgresql/16/extension/

# zhparser 內建中文字典與規則檔（zhparser make install 落到 PostgreSQL tsearch_data；
# zhparser.so 內 hardcode 讀取 /usr/share/postgresql/16/tsearch_data/dict.utf8.xdb，
# 缺檔會在 to_tsvector 第一次呼叫時 NOTICE "zhparser set dict ... failed" 並回空 lexeme）
COPY --from=builder /usr/share/postgresql/16/tsearch_data/dict.utf8.xdb /usr/share/postgresql/16/tsearch_data/
COPY --from=builder /usr/share/postgresql/16/tsearch_data/rules.utf8.ini /usr/share/postgresql/16/tsearch_data/

# 註冊 libscws.so.1 到 ld cache，否則 zhparser.so dlopen 找不到 libscws
RUN ldconfig

# 初始化腳本（容器首次啟動執行）
COPY init.sql /docker-entrypoint-initdb.d/init.sql
