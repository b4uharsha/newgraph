"""Request ID middleware for request tracing."""

import uuid
from collections.abc import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Middleware to ensure every request has a unique ID.

    If the incoming request has an X-Request-ID header, it's used.
    Otherwise, a new UUID is generated.

    The request ID is:
    - Stored in request.state.request_id for access in handlers
    - Added to the response as X-Request-ID header
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable,
    ) -> Response:
        """Process request and add request ID."""
        # Get existing request ID or generate new one
        request_id = request.headers.get("X-Request-ID")
        if not request_id:
            request_id = str(uuid.uuid4())

        # Store in request state for access in handlers
        request.state.request_id = request_id

        # Process request
        response = await call_next(request)

        # Add to response headers
        response.headers["X-Request-ID"] = request_id

        return response
