import uuid

import structlog
from fastapi import Request
from fastapi.responses import Response
from starlette.middleware.base import RequestResponseEndpoint


async def request_id_middleware(request: Request, call_next: RequestResponseEndpoint) -> Response:
    rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = rid
    with structlog.contextvars.bound_contextvars(request_id=rid):
        response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    return response
