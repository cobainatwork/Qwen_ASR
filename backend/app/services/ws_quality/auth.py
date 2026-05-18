"""WebSocket 認證（規格 §12 + 強制規範 12）。

格式：``Sec-WebSocket-Protocol: asr.v1, bearer.<base64url(token)>``
**禁止透過 query string 傳遞 token**（會被 access log / Referer 洩漏）。
"""

from __future__ import annotations

import base64
import binascii

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import WsAuthFailedError
from app.core.security import derive_hmac_key, lookup_prefix, verify_token_hash
from app.models import ApiKey
from app.repositories.api_key import ApiKeyRepository


def parse_subprotocols(header_value: str | None) -> tuple[bool, str | None]:
    """解析 Sec-WebSocket-Protocol header 為 (asr_v1_present, raw_token)。

    Args:
        header_value: ``Sec-WebSocket-Protocol`` header 的原始字串，或 None。

    Returns:
        ``(asr_v1_present, raw_token)``：
        - ``asr_v1_present``：header 中是否包含 ``asr.v1`` token。
        - ``raw_token``：解碼後的 bearer token，或 None（未提供時）。

    Raises:
        WsAuthFailedError: bearer 部分的 base64url 解碼失敗時。
    """
    if not header_value:
        return False, None

    parts = [p.strip() for p in header_value.split(",") if p.strip()]
    asr_v1 = "asr.v1" in parts

    raw_token: str | None = None
    for p in parts:
        if p.startswith("bearer."):
            b64 = p[len("bearer."):]
            try:
                padded = b64 + "=" * (-len(b64) % 4)
                raw_token = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
            except (binascii.Error, UnicodeDecodeError) as e:
                raise WsAuthFailedError(message="無法解析 bearer subprotocol") from e
            break

    return asr_v1, raw_token


def authenticate_websocket(
    header_value: str | None,
    db: Session,
    settings: Settings,
) -> ApiKey:
    """驗證 WebSocket subprotocol 並回傳對應 ApiKey。

    流程：
    1. 解析 ``Sec-WebSocket-Protocol`` header。
    2. 確認 ``asr.v1`` 存在。
    3. 確認 bearer token 存在。
    4. 以 HMAC 前綴查詢 DB 候選金鑰，逐一 Argon2id 驗證。
    5. 驗證成功後更新 ``last_used_at``，回傳 ApiKey ORM 物件。

    Args:
        header_value: ``Sec-WebSocket-Protocol`` header 值。
        db: SQLAlchemy Session（由 FastAPI Dependency 注入）。
        settings: 應用設定（含 ``API_KEY`` / ``LOOKUP_HMAC_KEY``）。

    Returns:
        通過驗證的 :class:`~app.models.ApiKey` ORM 物件。

    Raises:
        WsAuthFailedError: 任何認證失敗（``asr.v1`` 缺、token 缺、解析失敗、DB 無匹配）。
    """
    asr_v1, raw_token = parse_subprotocols(header_value)

    if not asr_v1:
        raise WsAuthFailedError(message="缺少 asr.v1 subprotocol")
    if not raw_token:
        raise WsAuthFailedError(message="缺少 bearer subprotocol")

    hmac_key: bytes
    if settings.LOOKUP_HMAC_KEY:
        hmac_key = settings.LOOKUP_HMAC_KEY.encode()
    else:
        hmac_key = derive_hmac_key(settings.API_KEY)

    prefix = lookup_prefix(raw_token, hmac_key)

    repo = ApiKeyRepository(db)
    candidates = repo.find_active_by_prefix(prefix)
    for key in candidates:
        if verify_token_hash(raw_token, key.key_hash):
            repo.touch_last_used(key)
            return key

    raise WsAuthFailedError(message="token 無效")
