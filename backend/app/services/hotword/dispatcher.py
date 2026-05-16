"""Hotword 三層分流決策器（規格 §13.4）。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import HotwordTooLargeError
from app.repositories.hotword import HotwordGroupRepository
from app.services.hotword.strategies import (
    CtcWsStrategy,
    HotwordStrategy,
    ShallowFusionStrategy,
)


def select_strategy(
    group_id: int,
    db: Session,
    api_key_id: int,
    settings: Settings | None = None,
) -> HotwordStrategy:
    """依群組詞數選擇策略。

    閾值可由 ENV 覆寫（HOTWORD_SHALLOW_FUSION_THRESHOLD / HOTWORD_CTC_WS_THRESHOLD）。

    Raises:
        HotwordTooLargeError: 詞數 ≥ CTC_WS_THRESHOLD，需走 Fine-tune。
    """
    s = settings or get_settings()
    word_count = HotwordGroupRepository(db, api_key_id).count_words(group_id)

    if word_count < s.HOTWORD_SHALLOW_FUSION_THRESHOLD:
        return ShallowFusionStrategy()
    if word_count < s.HOTWORD_CTC_WS_THRESHOLD:
        return CtcWsStrategy()
    raise HotwordTooLargeError(
        message=f"Hotword 群組 {group_id} 含 {word_count} 詞，超過 CTC-WS 上限",
        details={
            "group_id": group_id,
            "word_count": word_count,
            "limit": s.HOTWORD_CTC_WS_THRESHOLD,
            "suggested_endpoint": "/api/v1/finetune/tasks",
        },
    )
