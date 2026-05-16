import logging
import re
import sys
from collections.abc import MutableMapping
from typing import Any, cast

import structlog

# 敏感欄位黑名單
_SENSITIVE_KEYS = {
    "authorization",
    "api_key",
    "token",
    "password",
    "transcript_text",
    "asr_result",
    "audio_base64",
    "raw_token",
}

_BEARER_PATTERN = re.compile(r"Bearer\s+\S+", re.IGNORECASE)


def _redact_sensitive(
    _logger: Any, _name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """移除敏感欄位與遮蔽 Bearer token。"""
    for key in list(event_dict.keys()):
        if key.lower() in _SENSITIVE_KEYS:
            event_dict[key] = "[REDACTED]"
    for key, value in list(event_dict.items()):
        if isinstance(value, str) and _BEARER_PATTERN.search(value):
            event_dict[key] = _BEARER_PATTERN.sub("Bearer [REDACTED]", value)
    return event_dict


def configure_logging(level: str = "INFO", json_format: bool = True) -> None:
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper()),
    )

    processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _redact_sensitive,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    processors.append(
        structlog.processors.JSONRenderer() if json_format else structlog.dev.ConsoleRenderer()
    )

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level.upper())),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return cast(structlog.stdlib.BoundLogger, structlog.get_logger(name))
