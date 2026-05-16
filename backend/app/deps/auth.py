from collections.abc import Callable

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import (
    ForbiddenError,
    MissingBearerError,
    UnauthorizedError,
)
from app.core.security import derive_hmac_key, lookup_prefix, verify_token_hash
from app.deps.db import get_db
from app.models import ApiKey
from app.repositories.api_key import ApiKeyRepository


def get_current_tenant(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> ApiKey:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise MissingBearerError()
    raw_token = authorization.split(" ", 1)[1].strip()
    if not raw_token:
        raise MissingBearerError()

    settings = get_settings()
    hmac_key = (
        settings.LOOKUP_HMAC_KEY.encode()
        if settings.LOOKUP_HMAC_KEY
        else derive_hmac_key(settings.API_KEY)
    )
    prefix = lookup_prefix(raw_token, hmac_key)

    repo = ApiKeyRepository(db)
    candidates = repo.find_active_by_prefix(prefix)
    for key in candidates:
        if verify_token_hash(raw_token, key.key_hash):
            repo.touch_last_used(key)
            return key
    raise UnauthorizedError()


def require_scope(scope: str) -> Callable[..., ApiKey]:
    def _check(api_key: ApiKey = Depends(get_current_tenant)) -> ApiKey:
        if "admin" in api_key.scopes or scope in api_key.scopes:
            return api_key
        raise ForbiddenError(
            code="AUTH_SCOPE_INSUFFICIENT",
            message=f"需要 scope: {scope}",
            details={"required": scope, "granted": list(api_key.scopes)},
        )

    return _check
