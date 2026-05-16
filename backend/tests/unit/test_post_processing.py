from app.services.post_processing.numbers import normalize_numbers
from app.services.post_processing.pipeline import run_post_processing
from app.services.post_processing.punctuation import add_punctuation


def test_add_punctuation_end_with_period() -> None:
    assert add_punctuation("你好") == "你好。"


def test_add_punctuation_question() -> None:
    assert add_punctuation("這是什麼嗎") == "這是什麼嗎？"


def test_add_punctuation_keeps_existing() -> None:
    assert add_punctuation("你好。") == "你好。"


def test_normalize_numbers_simple() -> None:
    assert normalize_numbers("一二三") == "123"


def test_normalize_numbers_with_units() -> None:
    assert normalize_numbers("一百二十三") == "123"


def test_normalize_numbers_two() -> None:
    assert normalize_numbers("兩千零五") == "2005"


def test_normalize_numbers_preserves_text() -> None:
    assert normalize_numbers("我有三本書") == "我有3本書"


def test_run_pipeline_full() -> None:
    result = run_post_processing("我有三本書嗎")
    assert result.final_text == "我有3本書嗎？"
    assert len(result.stages) == 2
    assert all(s["status"] == "ok" for s in result.stages)


def test_run_pipeline_punctuation_disabled() -> None:
    result = run_post_processing("一二三", punctuation=False)
    assert result.final_text == "123"
    assert len(result.stages) == 1
