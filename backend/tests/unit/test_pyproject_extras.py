"""鎖 pyproject.toml extras 內容，防 application-code 引用的可選依賴漂移。

歷史背景：M9 youtube downloader 引用 yt_dlp 但任何 extras 未宣告，
deploy 後使用者點下載才現形（2026-05-19）。本測試確保 youtube
extras 一旦缺漏立即 pytest fail。
"""
from __future__ import annotations

import tomllib
from pathlib import Path


def _load_pyproject() -> dict:
    path = Path(__file__).resolve().parent.parent.parent / "pyproject.toml"
    with path.open("rb") as f:
        return tomllib.load(f)


def test_youtube_extra_declares_yt_dlp() -> None:
    """[project.optional-dependencies].youtube 必須含 yt-dlp。"""
    extras = _load_pyproject()["project"]["optional-dependencies"]
    assert "youtube" in extras, "[youtube] extras 區段缺失"
    deps = extras["youtube"]
    assert any(d.startswith("yt-dlp") for d in deps), (
        f"yt-dlp 未在 youtube extras 宣告，現有：{deps}"
    )


def test_audio_extra_declares_fireredvad() -> None:
    """既有 audio extras 守 fireredvad（與本修補無關，但同樣防漂移）。"""
    extras = _load_pyproject()["project"]["optional-dependencies"]
    deps = extras["audio"]
    assert any(d.startswith("fireredvad") for d in deps), (
        f"fireredvad 未在 audio extras 宣告，現有：{deps}"
    )


def test_gpu_extra_declares_qwen_asr_and_pyannote() -> None:
    """既有 gpu extras 守 qwen-asr + pyannote.audio。"""
    extras = _load_pyproject()["project"]["optional-dependencies"]
    deps = extras["gpu"]
    assert any(d.startswith("qwen-asr") for d in deps), f"qwen-asr 缺：{deps}"
    assert any(d.startswith("pyannote.audio") for d in deps), f"pyannote 缺：{deps}"
