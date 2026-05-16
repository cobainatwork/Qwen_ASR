from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Hotword, HotwordGroup
from app.repositories.base import TenantScopedRepository


class HotwordGroupRepository(TenantScopedRepository[HotwordGroup]):
    model = HotwordGroup

    def count_words(self, group_id: int) -> int:
        result = self.db.execute(
            select(func.count(Hotword.id)).where(Hotword.group_id == group_id)
        ).scalar_one()
        return int(result)

    def refresh_word_count(self, group_id: int) -> None:
        group = self.get(group_id)
        if group is None:
            return
        group.word_count = self.count_words(group_id)
        self.db.flush()


class HotwordRepository:
    """Hotword（單字）跨群組存取，不繼承 TenantScopedRepository。

    Tenant 隔離透過 group_id → HotwordGroup.api_key_id 驗證實現。
    """

    def __init__(self, db: Session, api_key_id: int) -> None:
        self.db = db
        self.api_key_id = api_key_id

    def list_by_group(self, group_id: int) -> list[Hotword]:
        return list(self.db.execute(
            select(Hotword).where(Hotword.group_id == group_id)
        ).scalars().all())

    def bulk_insert(self, group_id: int, words: list[dict[str, object]]) -> int:
        """批次新增 hotword，回傳新增筆數。

        words 格式：[{"word": "...", "weight": 1.0, "pinyin": "..."}]
        """
        for w in words:
            self.db.add(Hotword(
                group_id=group_id,
                word=w["word"],
                weight=w.get("weight", 1.0),
                pinyin=w.get("pinyin"),
            ))
        self.db.flush()
        return len(words)
