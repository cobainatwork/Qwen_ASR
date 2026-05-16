from typing import Any, Generic, TypeVar

from sqlalchemy.orm import Query, Session

from app.models.base import Base

T = TypeVar("T", bound=Base)


class TenantScopedRepository(Generic[T]):
    """Tenant 隔離資料存取層。

    繼承後設定 ``model: type[T]``，所有查詢會自動掛 api_key_id 過濾。
    """

    model: type[T]

    def __init__(self, db: Session, api_key_id: int) -> None:
        self.db = db
        self.api_key_id = api_key_id

    def _scoped_query(self) -> Query:  # type: ignore[type-arg]
        return self.db.query(self.model).filter(
            self.model.api_key_id == self.api_key_id  # type: ignore[attr-defined]
        )

    def get(self, id_: int) -> T | None:
        return self._scoped_query().filter(self.model.id == id_).one_or_none()  # type: ignore[attr-defined]

    def list(self, limit: int = 50, offset: int = 0) -> list[T]:
        return self._scoped_query().limit(limit).offset(offset).all()

    def create(self, **kwargs: Any) -> T:
        instance = self.model(**kwargs, api_key_id=self.api_key_id)
        self.db.add(instance)
        self.db.flush()
        return instance

    def update(self, instance: T, **changes: Any) -> T:
        if getattr(instance, "api_key_id", None) != self.api_key_id:
            raise PermissionError("跨租戶 update")
        for k, v in changes.items():
            setattr(instance, k, v)
        self.db.flush()
        return instance

    def delete(self, instance: T) -> None:
        if getattr(instance, "api_key_id", None) != self.api_key_id:
            raise PermissionError("跨租戶 delete")
        self.db.delete(instance)
        self.db.flush()
