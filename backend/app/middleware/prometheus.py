"""Phase 2 啟用：Prometheus metrics middleware。"""

from fastapi import Request
from fastapi.responses import Response
from starlette.middleware.base import RequestResponseEndpoint


async def prometheus_middleware(request: Request, call_next: RequestResponseEndpoint) -> Response:
    # Phase 2: 增加 request_count / duration histogram
    return await call_next(request)
