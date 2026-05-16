import pytest
from app.core.exceptions import (
    ALL_ERROR_CODES,
    AppException,
    DatasetNotFoundError,
    DatasetSampleInvalidError,
    ForbiddenError,
    HotwordGroupNotFoundError,
    HotwordTooLargeError,
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


def test_m5_error_codes_defaults() -> None:
    assert HotwordGroupNotFoundError().code == "HOTWORD_GROUP_NOT_FOUND"
    assert HotwordGroupNotFoundError().http_status == 404
    assert HotwordTooLargeError().http_status == 422
    assert DatasetNotFoundError().http_status == 404
    assert DatasetSampleInvalidError().http_status == 400


def test_all_error_codes_includes_m5() -> None:
    assert "HOTWORD_GROUP_NOT_FOUND" in ALL_ERROR_CODES
    assert "HOTWORD_TOO_LARGE" in ALL_ERROR_CODES
    assert "DATASET_NOT_FOUND" in ALL_ERROR_CODES
    assert "DATASET_SAMPLE_INVALID" in ALL_ERROR_CODES
