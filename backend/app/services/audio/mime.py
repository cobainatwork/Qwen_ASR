"""音檔 MIME 校驗（magic bytes，不依賴副檔名）。"""

from __future__ import annotations

from app.core.exceptions import AudioMimeInvalidError

# python-magic 偵測結果與允許副檔名的對應
_MIME_TO_EXT = {
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/mp4": "mp4",
    "video/mp4": "mp4",
    "audio/x-m4a": "m4a",
    "audio/m4a": "m4a",
    "audio/flac": "flac",
    "audio/x-flac": "flac",
    "audio/ogg": "ogg",
    "audio/aac": "aac",
    "audio/x-aac": "aac",
    "video/webm": "webm",
    "audio/webm": "webm",
}


def verify_mime(buf: bytes, supported_formats: list[str]) -> tuple[str, str]:
    """檢查二進位內容是否為支援的音/視訊格式。

    Returns:
        (verified_mime_type, canonical_extension)

    Raises:
        AudioMimeInvalidError: 非音/視訊或副檔名不在白名單。
    """
    if not buf:
        raise AudioMimeInvalidError(message="檔案為空")

    try:
        import magic  # 延遲 import：audio optional deps 未安裝時不影響啟動
    except ImportError as e:
        raise RuntimeError(
            "python-magic 套件未安裝。請以 INSTALL_AUDIO_DEPS=true 重建映像。"
        ) from e

    detected = magic.from_buffer(buf, mime=True)
    if not (detected.startswith("audio/") or detected.startswith("video/")):
        raise AudioMimeInvalidError(
            message=f"非音/視訊內容：{detected}",
            details={"detected_mime": detected},
        )

    ext = _MIME_TO_EXT.get(detected)
    if ext is None:
        raise AudioMimeInvalidError(
            message=f"未支援的 MIME 類型：{detected}",
            details={"detected_mime": detected},
        )
    if ext not in {e.strip().lower() for e in supported_formats}:
        raise AudioMimeInvalidError(
            message=f"格式 {ext} 不在白名單",
            details={"detected_mime": detected, "extension": ext},
        )
    return detected, ext
