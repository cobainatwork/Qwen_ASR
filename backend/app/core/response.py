from typing import Any, TypeVar

from app.schemas.common import ErrorDetail, ResponseEnvelope

T = TypeVar("T")


def success(data: T) -> ResponseEnvelope[T]:
    return ResponseEnvelope[T](success=True, data=data, error=None)


def failure(
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> ResponseEnvelope[None]:
    return ResponseEnvelope[None](
        success=False,
        data=None,
        error=ErrorDetail(code=code, message=message, details=details),
    )
