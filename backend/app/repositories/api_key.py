from sqlalchemy.orm import Session

from app.models import ApiKey


class ApiKeyRepository:
    """跨租戶的 api_keys 存取（不繼承 TenantScopedRepository）。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def find_active_by_prefix(self, prefix: str) -> list[ApiKey]:
        return (
            self.db.query(ApiKey)
            .filter(
                ApiKey.lookup_prefix == prefix,
                ApiKey.deleted_at.is_(None),
                ApiKey.is_active.is_(True),
            )
            .all()
        )

    def touch_last_used(self, api_key: ApiKey) -> None:
        from sqlalchemy import func

        api_key.last_used_at = func.now()
        self.db.flush()
