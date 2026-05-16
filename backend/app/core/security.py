import hashlib
import hmac

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHash, VerifyMismatchError

# 規格 19.1 + 設計 PHASE1-SPEC-01 補丁
_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
)


def hash_token(raw_token: str) -> str:
    """以 Argon2id 雜湊原始 token。"""
    return _hasher.hash(raw_token)


def verify_token_hash(raw_token: str, stored_hash: str) -> bool:
    """驗證 raw_token 是否符合儲存的 Argon2id 雜湊。"""
    try:
        _hasher.verify(stored_hash, raw_token)
        return True
    except (VerifyMismatchError, InvalidHash):
        return False


def lookup_prefix(raw_token: str, hmac_key: bytes) -> str:
    """產生用於 DB 索引查找的前綴。

    使用 HMAC-SHA256 而非直接 SHA256，避免攻擊者透過離線
    rainbow table 反推 raw_token。前 16 hex chars 提供 64-bit
    namespace，碰撞機率足夠低（< 10 萬筆金鑰下碰撞 < 1%）。
    """
    if not hmac_key:
        raise ValueError("hmac_key 不可為空")
    digest = hmac.new(hmac_key, raw_token.encode("utf-8"), hashlib.sha256).hexdigest()
    return digest[:16]


def derive_hmac_key(api_key_env: str) -> bytes:
    """以 process-wide API_KEY 衍生 HMAC 密鑰。

    僅 Phase 1 使用。Phase 2 應改為獨立 LOOKUP_HMAC_KEY 環境變數。
    """
    return hashlib.sha256(("lookup-prefix-v1::" + api_key_env).encode("utf-8")).digest()
