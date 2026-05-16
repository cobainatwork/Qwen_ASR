"""Audit log 服務。

提供 record_audit_event 函式，以 raw SQL 寫入 audit_logs 表，
避免 ORM 層與 SQLAlchemy Base.metadata 屬性命名衝突。
"""

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def record_audit_event(
    db: Session,
    event_type: str,
    *,
    api_key_id: int | None = None,
    target_api_key_id: int | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """將稽核事件寫入 audit_logs 表。

    參數：
        db: SQLAlchemy Session。
        event_type: 事件類型字串（如 auth.key_created）。
        api_key_id: 觸發事件的 API 金鑰 ID（可選）。
        target_api_key_id: 受影響的目標 API 金鑰 ID（可選）。
        ip_address: 請求來源 IP（可選）。
        user_agent: 請求 User-Agent（可選）。
        metadata: 任意 JSONB 附加資料（可選）。

    備註：
        psycopg3 的 raw SQL 不支援直接傳遞 Python dict 給 JSONB 欄位。
        使用 ::jsonb cast 將 JSON 字串轉換，確保跨驅動相容。
    """
    # 將 metadata dict 序列化為 JSON 字串，再透過 ::jsonb cast 寫入。
    # NULL 時直接傳 None，讓 SQL 處理為 NULL JSONB。
    metadata_json: str | None = (
        json.dumps(metadata, ensure_ascii=False) if metadata is not None else None
    )

    db.execute(
        text(
            "INSERT INTO audit_logs "
            "(event_type, api_key_id, target_api_key_id, ip_address, user_agent, metadata) "
            "VALUES (:e, :a, :t, :i, :u, CAST(:m AS jsonb))"
        ),
        {
            "e": event_type,
            "a": api_key_id,
            "t": target_api_key_id,
            "i": ip_address,
            "u": user_agent,
            "m": metadata_json,
        },
    )
