"""YouTube URL SSRF 防護驗證（規格 §3.3.7 + §14.2）。"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from app.core.config import Settings
from app.core.exceptions import YoutubeUrlInvalidError

_YOUTUBE_PATTERNS = [
    re.compile(r"^https://(?:www\.)?youtube\.com/watch\?v=[\w-]{6,20}(?:&|$)"),
    re.compile(r"^https://youtu\.be/[\w-]{6,20}(?:\?|$)"),
    re.compile(r"^https://(?:www\.)?youtube\.com/embed/[\w-]{6,20}(?:\?|$)"),
]


def validate_youtube_url(url: str, settings: Settings) -> str:
    """驗證 URL 符合白名單與模式，回傳正規化後 URL。

    Raises:
        YoutubeUrlInvalidError: 任何不符合的條件
    """
    if not url:
        raise YoutubeUrlInvalidError(message="URL 為空")

    if not url.startswith("https://"):
        raise YoutubeUrlInvalidError(
            message="僅接受 https",
            details={"url": url[:200]},
        )

    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise YoutubeUrlInvalidError(details={"scheme": parsed.scheme})

    host = (parsed.hostname or "").lower().removeprefix("www.")
    whitelist = settings.youtube_whitelist_set
    if host not in whitelist:
        raise YoutubeUrlInvalidError(
            details={"host": host, "whitelist": sorted(whitelist)},
        )

    if not any(p.match(url) for p in _YOUTUBE_PATTERNS):
        raise YoutubeUrlInvalidError(
            message="URL 路徑不符合預期格式",
            details={"url": url[:200]},
        )

    return url
