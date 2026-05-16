"""Bootstrap admin 金鑰服務。

於應用程式啟動時，若 api_keys 表為空（無任何有效金鑰），
自動以環境變數 API_KEY 建立一組 admin scope 的初始金鑰。
"""

import structlog
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import derive_hmac_key, hash_token, lookup_prefix
from app.models import ApiKey
from app.services.audit import record_audit_event

logger = structlog.get_logger(__name__)


def bootstrap_admin_key(db: Session, settings: Settings) -> None:
    """若 api_keys 表為空，自動建立 bootstrap admin 金鑰。

    邏輯：
    1. 計算未刪除的 api_keys 數量。
    2. 若 count > 0，直接回傳（跳過）。
    3. 否則以 settings.API_KEY 建立 admin scope 金鑰，並寫入 audit event。

    參數：
        db: SQLAlchemy Session（由呼叫端管理 transaction）。
        settings: 應用程式設定實例。
    """
    count = db.query(ApiKey).filter(ApiKey.deleted_at.is_(None)).count()
    if count > 0:
        return

    hmac_key = (
        settings.LOOKUP_HMAC_KEY.encode()
        if settings.LOOKUP_HMAC_KEY
        else derive_hmac_key(settings.API_KEY)
    )
    key = ApiKey(
        key_hash=hash_token(settings.API_KEY),
        lookup_prefix=lookup_prefix(settings.API_KEY, hmac_key),
        name="bootstrap-admin",
        description="啟動時自動建立的管理員金鑰",
        scopes=["admin"],
    )
    db.add(key)
    db.flush()
    record_audit_event(
        db,
        "auth.key_created",
        target_api_key_id=key.id,
        metadata={"reason": "bootstrap"},
    )
    db.commit()
    logger.info("bootstrap admin key created", api_key_id=key.id)
