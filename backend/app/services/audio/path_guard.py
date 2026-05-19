"""音檔 storage_path 守衛：存在性 + containment（修 adversarial review C1）。"""
from __future__ import annotations

from pathlib import Path

from app.core.exceptions import NotFoundError, ValidationFailedError


def ensure_safe_audio_path(path: Path | str, *, base_dir: Path | str) -> Path:
    """確認 path 解析後位於 base_dir 內且檔案存在；不符合拋對應 AppException。

    對抗兩類風險：
    1. _execute_download race / 保留期掃描刪檔 → FileNotFoundError 500 leak。
    2. 任何路徑構造 bug 寫入超出 AUDIO_STORAGE_DIR 的 storage_path（含 symlink）。
    """
    resolved = Path(path).resolve()
    base_resolved = Path(base_dir).resolve()
    if not resolved.is_relative_to(base_resolved):
        raise ValidationFailedError(message="音檔路徑超出允許範圍")
    if not resolved.is_file():
        raise NotFoundError(message="音檔檔案不存在")
    return resolved
