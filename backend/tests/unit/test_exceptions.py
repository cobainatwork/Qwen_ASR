import pytest
from app.core.exceptions import (
    ALL_ERROR_CODES,
    AppException,
    ForbiddenError,
    MissingBearerError,
    UnauthorizedError,
)


def test_app_exception_defaults() -> None:
    exc = AppException()
    assert exc.code == "INTERNAL_ERROR"
    assert exc.http_status == 500


def test_app_exception_override() -> None:
    exc = AppException(code="CUSTOM", message="msg", http_status=418, details={"k": "v"})
    assert exc.code == "CUSTOM"
    assert exc.http_status == 418
    assert exc.details == {"k": "v"}


@pytest.mark.parametrize(
    "exc_cls,code,status",
    [
        (UnauthorizedError, "AUTH_INVALID_TOKEN", 401),
        (MissingBearerError, "AUTH_MISSING_BEARER", 401),
        (ForbiddenError, "AUTH_SCOPE_INSUFFICIENT", 403),
    ],
)
def test_subclass_defaults(exc_cls: type[AppException], code: str, status: int) -> None:
    exc = exc_cls()
    assert exc.code == code
    assert exc.http_status == status


def test_all_error_codes_unique() -> None:
    assert len(ALL_ERROR_CODES) == len(set(ALL_ERROR_CODES))


def test_all_error_codes_at_least_20() -> None:
    assert len(ALL_ERROR_CODES) >= 20
