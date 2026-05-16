"""Phase 2 啟用：Idempotency-Key 解析與重放。"""

from fastapi import Request
from fastapi.responses import Response
from starlette.middleware.base import RequestResponseEndpoint


async def idempotency_middleware(request: Request, call_next: RequestResponseEndpoint) -> Response:
    # Phase 2: 讀 Idempotency-Key header、Redis 查重
    return await call_next(request)
