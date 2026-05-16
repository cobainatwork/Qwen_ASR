import pytest
from app.core.config import Settings
from app.core.exceptions import HotwordTooLargeError
from app.models import Hotword, HotwordGroup
from app.services.hotword.dispatcher import select_strategy
from app.services.hotword.strategies import CtcWsStrategy, ShallowFusionStrategy
from sqlalchemy.orm import Session


def _make_settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "API_KEY": "k",
        "DATABASE_URL": "postgresql+psycopg://u:p@h/d",
        "DB_PASSWORD": "p",
        "THIRD_PARTY_LICENSE_ACK": True,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def _seed_group(db: Session, api_key_id: int, word_count: int) -> int:
    group = HotwordGroup(api_key_id=api_key_id, name="test")
    db.add(group)
    db.flush()
    for i in range(word_count):
        db.add(Hotword(group_id=group.id, word=f"word{i}"))
    db.flush()
    return group.id


def test_under_100_returns_shallow_fusion(db_session: Session, seed_api_key: int) -> None:
    group_id = _seed_group(db_session, seed_api_key, word_count=50)
    strategy = select_strategy(group_id, db_session, seed_api_key, settings=_make_settings())
    assert isinstance(strategy, ShallowFusionStrategy)


def test_between_100_and_1000_returns_ctc_ws(db_session: Session, seed_api_key: int) -> None:
    group_id = _seed_group(db_session, seed_api_key, word_count=500)
    strategy = select_strategy(group_id, db_session, seed_api_key, settings=_make_settings())
    assert isinstance(strategy, CtcWsStrategy)


def test_at_or_above_1000_raises_too_large(db_session: Session, seed_api_key: int) -> None:
    group_id = _seed_group(db_session, seed_api_key, word_count=1000)
    with pytest.raises(HotwordTooLargeError) as exc:
        select_strategy(group_id, db_session, seed_api_key, settings=_make_settings())
    assert exc.value.details["word_count"] == 1000
    assert exc.value.details["suggested_endpoint"] == "/api/v1/finetune/tasks"


def test_empty_group_returns_shallow_fusion(db_session: Session, seed_api_key: int) -> None:
    group_id = _seed_group(db_session, seed_api_key, word_count=0)
    strategy = select_strategy(group_id, db_session, seed_api_key, settings=_make_settings())
    assert isinstance(strategy, ShallowFusionStrategy)
