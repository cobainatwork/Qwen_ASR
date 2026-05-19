from __future__ import annotations

from pathlib import Path

import pytest
from app.core.exceptions import NotFoundError, ValidationFailedError
from app.services.audio.path_guard import ensure_safe_audio_path


def test_existing_file_inside_base_returns_resolved(tmp_path: Path) -> None:
    p = tmp_path / "ok.wav"
    p.write_bytes(b"RIFF")
    assert ensure_safe_audio_path(p, base_dir=tmp_path) == p.resolve()


def test_missing_file_raises_not_found(tmp_path: Path) -> None:
    with pytest.raises(NotFoundError, match="不存在"):
        ensure_safe_audio_path(tmp_path / "ghost.wav", base_dir=tmp_path)


def test_path_outside_base_raises_validation(tmp_path: Path) -> None:
    outside = tmp_path / ".." / "escape.wav"
    with pytest.raises(ValidationFailedError, match="路徑"):
        ensure_safe_audio_path(outside, base_dir=tmp_path)


def test_symlink_escaping_base_raises_validation(tmp_path: Path) -> None:
    target = tmp_path.parent / "secret.wav"
    target.write_bytes(b"X")
    link = tmp_path / "sneaky.wav"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("Windows 缺 symlink 權限時跳過")
    with pytest.raises(ValidationFailedError, match="路徑"):
        ensure_safe_audio_path(link, base_dir=tmp_path)
