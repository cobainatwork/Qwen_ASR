from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models import ApiKey


class ApiKeyRepository:
    """跨租戶的 api_keys 存取（不繼承 TenantScopedRepository）。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def find_active_by_prefix(self, prefix: str) -> list[ApiKey]:
        """回傳同 lookup_prefix 且仍有效的金鑰。

        有效 = ``deleted_at IS NULL`` 且 ``is_active = TRUE`` 且未過期（``expires_at
        IS NULL OR expires_at > NOW()``）。過期金鑰會直接從候選列表排除，
        ``get_current_tenant`` 隨後 fall through 到 ``UnauthorizedError``，與
        規格 §19.1 line 2740「比對失敗 / 已停用 / 已軟刪除 / 已過期 → 401」
        共用 401 路徑。
        """
        return (
            self.db.query(ApiKey)
            .filter(
                ApiKey.lookup_prefix == prefix,
                ApiKey.deleted_at.is_(None),
                ApiKey.is_active.is_(True),
                or_(ApiKey.expires_at.is_(None), ApiKey.expires_at > func.now()),
            )
            .all()
        )

    def touch_last_used(self, api_key: ApiKey) -> None:
        from sqlalchemy import func

        api_key.last_used_at = func.now()
        self.db.flush()
