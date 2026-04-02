"""No-op auth handler -- allows all requests (development mode)."""

from __future__ import annotations

from langrove.auth.base import AuthHandler, AuthUser


class NoopAuthHandler(AuthHandler):
    """Always authenticates. Used in development mode."""

    async def authenticate(self, headers: dict[str, str]) -> AuthUser:
        return AuthUser(identity="anonymous", role="admin")
