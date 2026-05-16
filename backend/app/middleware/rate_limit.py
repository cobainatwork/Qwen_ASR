"""Phase 2 啟用：slowapi sliding window 限流。"""

from fastapi import Request
from fastapi.responses import Response
from starlette.middleware.base import RequestResponseEndpoint


async def rate_limit_middleware(request: Request, call_next: RequestResponseEndpoint) -> Response:
    # Phase 2: 依 api_key_id 限流
    return await call_next(request)
