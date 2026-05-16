import pytest
from app.core.config import Settings
from app.core.exceptions import YoutubeUrlInvalidError
from app.services.youtube.url_validator import validate_youtube_url


def _settings(whitelist: str = "youtube.com,youtu.be") -> Settings:
    return Settings(
        API_KEY="t",
        DATABASE_URL="postgresql+psycopg://u:p@h/d",
        DB_PASSWORD="p",
        THIRD_PARTY_LICENSE_ACK=True,
        YOUTUBE_DOMAIN_WHITELIST=whitelist,
    )  # type: ignore[call-arg]


@pytest.mark.parametrize("url", [
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "https://youtube.com/watch?v=abc12345",
    "https://youtu.be/dQw4w9WgXcQ",
    "https://www.youtube.com/embed/dQw4w9WgXcQ",
])
def test_valid_urls(url: str) -> None:
    assert validate_youtube_url(url, _settings()) == url


@pytest.mark.parametrize("url", [
    "http://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "https://evil.com/youtube.com/watch?v=x",
    "https://www.youtube.com.evil.com/watch?v=x",
    "https://vimeo.com/123456",
    "javascript:alert(1)",
    "",
    "https://www.youtube.com/redirect?url=evil",
    "https://www.youtube.com/",
])
def test_invalid_urls(url: str) -> None:
    with pytest.raises(YoutubeUrlInvalidError):
        validate_youtube_url(url, _settings())


def test_custom_whitelist() -> None:
    s = _settings(whitelist="example.com")
    with pytest.raises(YoutubeUrlInvalidError):
        validate_youtube_url("https://www.youtube.com/watch?v=abc12345", s)
