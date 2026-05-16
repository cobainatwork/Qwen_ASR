"""Phase 2 啟用：OpenTelemetry tracing middleware。"""

from fastapi import Request
from fastapi.responses import Response
from starlette.middleware.base import RequestResponseEndpoint


async def tracing_middleware(request: Request, call_next: RequestResponseEndpoint) -> Response:
    # Phase 2: 建立 OTEL span，注入 trace_id
    return await call_next(request)
