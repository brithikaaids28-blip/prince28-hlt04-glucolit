"""Request ID, request timing and crash handling."""

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from glucolit.logging_setup import request_id_ctx

logger = logging.getLogger(__name__)


class RequestMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
        request.state.request_id = request_id

        token = request_id_ctx.set(request_id)
        start_time = time.perf_counter()

        try:
            try:
                response = await call_next(request)
            except Exception:
                logger.exception(
                    "request failed",
                    extra={"request_id": request_id},
                )
                raise

            duration = round((time.perf_counter() - start_time) * 1000, 2)

            response.headers["X-Request-ID"] = request_id

            logger.info(
                "request completed",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": duration,
                },
            )

            return response
        finally:
            request_id_ctx.reset(token)
