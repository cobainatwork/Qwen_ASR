"""啟動前置檢查。

run_startup_checks 執行 6 項強制條件，任何一項失敗即以 sys.exit 中止程序。
規格依據：
- 第三方授權檢查：規格 26 節
- BACKEND_TYPE=vllm：規格 3.1 節
- VAD 警告：規格 6.1 節
- AUDIO_STORAGE_DIR 可寫：規格 12 節
- Production docs auth：規格 3.6 節
- DB 連線：可觀測性 / 啟動健康原則
"""

import os
import sys
from pathlib import Path

import structlog
from sqlalchemy import create_engine, text

from app.core.config import Settings

logger = structlog.get_logger(__name__)


def run_startup_checks(settings: Settings) -> None:
    """執行 6 項啟動前置檢查。

    任何一項失敗皆呼叫 sys.exit，阻止應用程式啟動。

    參數：
        settings: 應用程式設定實例。
    """
    # 檢查 1：第三方授權（規格 26 節）
    if not settings.THIRD_PARTY_LICENSE_ACK:
        sys.exit("THIRD_PARTY_LICENSE_ACK 未設定為 true，依規格 26 節拒絕啟動")

    # 檢查 2：推理後端必須為 vllm（規格 3.1 節）
    if settings.BACKEND_TYPE != "vllm":
        sys.exit(f"BACKEND_TYPE 必須為 'vllm'，目前為 '{settings.BACKEND_TYPE}'")

    # 檢查 3：VAD 關閉警告（規格 6.1 節）
    if not settings.VAD_ENABLED:
        logger.warning("VAD_ENABLED=false 違反規格 6.1 推薦，建議改為 true")

    # 檢查 4：AUDIO_STORAGE_DIR 可寫
    audio_dir = Path(settings.AUDIO_STORAGE_DIR)
    audio_dir.mkdir(parents=True, exist_ok=True)
    if not os.access(audio_dir, os.W_OK):
        sys.exit(f"AUDIO_STORAGE_DIR 不可寫：{audio_dir}")

    # 檢查 5：Production 模式強制啟用 docs 認證
    if settings.ENV == "production" and not settings.OPENAPI_DOCS_REQUIRE_AUTH:
        sys.exit("Production 模式必須 OPENAPI_DOCS_REQUIRE_AUTH=true")

    # 檢查 6：DB 連線驗證
    try:
        engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
    except Exception as e:
        sys.exit(f"資料庫連線失敗：{e}")
