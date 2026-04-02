"""FastAPI auth middleware."""

from __future__ import annotations

from typing import Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from langrove.auth.base import AuthHandler, AuthUser
from langrove.exceptions import AuthError


class AuthMiddleware(BaseHTTPMiddleware):
    """Authenticates requests using the configured AuthHandler.

    Skips auth for health endpoints and docs.
    """

    # Paths that don't require authentication
    SKIP_PATHS = {"/ok", "/health", "/info", "/docs", "/openapi.json", "/redoc"}

    def __init__(self, app: Any, handler: AuthHandler):
        super().__init__(app)
        self._handler = handler

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Skip auth for health/docs endpoints
        if request.url.path in self.SKIP_PATHS:
            return await call_next(request)

        # Extract headers
        headers = {k: v for k, v in request.headers.items()}

        try:
            user = await self._handler.authenticate(headers)
        except AuthError as e:
            from fastapi.responses import JSONResponse

            return JSONResponse(
                status_code=401,
                content={"code": "unauthorized", "message": str(e)},
            )
        except Exception as e:
            from fastapi.responses import JSONResponse

            return JSONResponse(
                status_code=500,
                content={"code": "auth_error", "message": str(e)},
            )

        if user is None:
            from fastapi.responses import JSONResponse

            return JSONResponse(
                status_code=401,
                content={"code": "unauthorized", "message": "Authentication failed"},
            )

        # Store user in request state for downstream access
        request.state.user = user

        return await call_next(request)
