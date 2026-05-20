from app.services.post_processing.numbers import normalize_numbers
from app.services.post_processing.pipeline import run_post_processing
from app.services.post_processing.punctuation import add_punctuation
from app.services.post_processing.s2t import convert_s2twp


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


def test_s2t_simplified_to_traditional_char() -> None:
    """字級簡轉繁：软 → 軟，质 → 質。"""
    assert convert_s2twp("软件") == "軟體"
    assert convert_s2twp("学习") == "學習"


def test_s2t_taiwan_vocab_phrase_level() -> None:
    """s2twp 啟用 Taiwan 詞彙：用户 → 使用者、优化 → 最佳化。"""
    assert convert_s2twp("用户优化体验") == "使用者最佳化體驗"


def test_s2t_taiwan_vocab_tech_terms() -> None:
    """OpenCC 1.3.x s2twp 對常見技術詞彙的覆蓋：滑鼠、記憶體、頻寬、伺服器、解析度。"""
    assert convert_s2twp("鼠标和键盘") == "滑鼠和鍵盤"
    assert convert_s2twp("内存条") == "記憶體條"
    assert convert_s2twp("网络带宽") == "網路頻寬"
    assert convert_s2twp("服务器") == "伺服器"


def test_s2t_taiwan_overrides_strong_terms() -> None:
    """Taiwan 強用語：OpenCC 給的「賬號 / 反饋 / 軟盤」由 overrides 補強。"""
    assert convert_s2twp("登录账号") == "登入帳號"  # 账号 → 賬號（OpenCC）→ 帳號（override）
    assert convert_s2twp("收集用户反馈") == "收集使用者回饋"  # 反馈 → 反饋（OpenCC）→ 回饋
    assert convert_s2twp("插入软盘") == "插入軟碟"  # 软盘 → 軟盤 → 軟碟


def test_s2t_already_traditional_unchanged() -> None:
    assert convert_s2twp("繁體中文不變") == "繁體中文不變"


def test_s2t_ascii_passthrough() -> None:
    assert convert_s2twp("hello world 123") == "hello world 123"


def test_s2t_empty_string() -> None:
    assert convert_s2twp("") == ""


def test_run_pipeline_full() -> None:
    """pipeline 應依序 punctuation → s2t → numbers 三段全 ok。"""
    result = run_post_processing("我有三本书嗎")
    # 簡 "书" → 繁 "書"，然後數字「三本」→ "3本"
    assert result.final_text == "我有3本書嗎？"
    assert len(result.stages) == 3
    assert [s["stage"] for s in result.stages] == ["punctuation", "s2t", "numbers"]
    assert all(s["status"] == "ok" for s in result.stages)


def test_run_pipeline_s2t_before_numbers() -> None:
    """spec §6 line 440：簡繁轉換必須先於數字轉換。簡體「五」必先變繁體再被數字化。"""
    # "五本书" → punctuation "五本书。" → s2t "五本書。" → numbers "5本書。"
    result = run_post_processing("五本书")
    assert result.final_text == "5本書。"


def test_run_pipeline_punctuation_disabled() -> None:
    result = run_post_processing("一二三", punctuation=False)
    assert result.final_text == "123"
    # s2t + numbers 都跑（punctuation 關閉），其他保留
    assert [s["stage"] for s in result.stages] == ["s2t", "numbers"]
