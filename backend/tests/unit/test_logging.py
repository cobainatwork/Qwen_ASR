import json
from io import StringIO

import pytest
import structlog
from app.core.logging import configure_logging, get_logger


@pytest.fixture(autouse=True)
def _reset_structlog() -> None:
    yield
    structlog.reset_defaults()


def _capture_log(callable_: callable) -> dict:
    buf = StringIO()
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(buf),
        cache_logger_on_first_use=False,
    )
    callable_()
    return json.loads(buf.getvalue().splitlines()[-1])


def test_get_logger_returns_bound_logger() -> None:
    configure_logging(level="INFO")
    logger = get_logger("test")
    assert hasattr(logger, "info")


def test_redact_authorization_header() -> None:
    configure_logging(level="INFO")
    buf = StringIO()
    structlog.configure(
        processors=[structlog.processors.JSONRenderer()],
        logger_factory=structlog.PrintLoggerFactory(buf),
        cache_logger_on_first_use=False,
    )
    from app.core.logging import _redact_sensitive

    event = _redact_sensitive(None, "info", {"authorization": "Bearer secret-token"})
    assert event["authorization"] == "[REDACTED]"


def test_redact_bearer_in_message() -> None:
    from app.core.logging import _redact_sensitive

    event = _redact_sensitive(None, "info", {"message": "got header: Bearer abc123 from client"})
    assert "abc123" not in event["message"]
    assert "[REDACTED]" in event["message"]


def test_redact_transcript_text() -> None:
    from app.core.logging import _redact_sensitive

    event = _redact_sensitive(None, "info", {"transcript_text": "客戶機密內容"})
    assert event["transcript_text"] == "[REDACTED]"


def test_configure_logging_produces_json() -> None:
    buf = StringIO()
    configure_logging(level="INFO", json_format=True)
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(buf),
        cache_logger_on_first_use=False,
    )
    logger = structlog.get_logger("t")
    logger.info("hello", extra_key=42)
    out = buf.getvalue().strip().splitlines()[-1]
    parsed = json.loads(out)
    assert parsed["event"] == "hello"
    assert parsed["extra_key"] == 42
