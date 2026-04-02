"""Base class for auth handlers."""

from __future__ import annotations

from typing import Any


class AuthUser:
    """Authenticated user info."""

    __slots__ = ("identity", "role", "metadata")

    def __init__(self, identity: str, role: str = "user", **metadata):
        self.identity = identity
        self.role = role
        self.metadata = metadata


class AuthHandler:
    """Base class for authentication handlers.

    Subclass and override authenticate() to implement custom auth.
    """

    async def authenticate(self, headers: dict[str, str]) -> AuthUser | None:
        """Authenticate a request from its headers.

        Returns AuthUser if valid, None to reject.
        Raise an exception to return a specific error.
        """
        raise NotImplementedError
