"""確認 main.py lifespan 不再主動載入 AlignerService。

驗證方式：搜尋 main.py 原始碼，確認不含 `AlignerService.load` 呼叫。
"""
import pathlib


def test_main_py_does_not_call_aligner_service_load() -> None:
    main_py = pathlib.Path("app/main.py").read_text(encoding="utf-8")
    assert "AlignerService.load" not in main_py, (
        "main.py lifespan 仍含 AlignerService.load()，"
        "應在 M4-revisit 中移除（ForcedAligner 已內建於 qwen-asr）"
    )


def test_aligner_service_has_deprecation_header() -> None:
    """確認 AlignerService 已標記為 offline-only 工具。"""
    aligner_py = pathlib.Path("app/services/aligner/service.py").read_text(encoding="utf-8")
    assert "DEPRECATED 主流程依賴" in aligner_py, (
        "aligner/service.py 缺少 M4-revisit deprecation header"
    )
