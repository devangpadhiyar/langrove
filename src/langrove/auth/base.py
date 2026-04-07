"""Base types for auth handlers."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from langgraph_sdk.auth.types import BaseUser


class AuthUser:
    """Concrete implementation of ``langgraph_sdk.auth.types.BaseUser``.

    Wraps the dict returned by authenticate handlers into an object that
    satisfies the BaseUser protocol, so it can be passed as ``ctx.user``
    to authorization handlers.
    """

    __slots__ = ("_identity", "_display_name", "_permissions", "_data")

    def __init__(
        self,
        identity: str,
        display_name: str = "",
        permissions: Sequence[str] = (),
        **extra: Any,
    ):
        self._identity = identity
        self._display_name = display_name or identity
        self._permissions = tuple(permissions)
        self._data: dict[str, Any] = {
            "identity": identity,
            "display_name": self._display_name,
            "permissions": self._permissions,
            "is_authenticated": True,
            **extra,
        }

    # --- BaseUser protocol properties ---

    @property
    def identity(self) -> str:
        return self._identity

    @property
    def display_name(self) -> str:
        return self._display_name

    @property
    def permissions(self) -> Sequence[str]:
        return self._permissions

    @property
    def is_authenticated(self) -> bool:
        return True

    # --- BaseUser protocol dict-like access ---

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __contains__(self, key: object) -> bool:
        return key in self._data

    def __iter__(self):
        return iter(self._data)

    # --- Langrove helpers ---

    @property
    def metadata(self) -> dict[str, Any]:
        """Extra fields beyond the standard BaseUser properties."""
        return {
            k: v
            for k, v in self._data.items()
            if k not in ("identity", "display_name", "permissions", "is_authenticated")
        }

    def to_dict(self) -> dict[str, Any]:
        """Serialize for injection into graph configurable."""
        return dict(self._data)


# Runtime check that AuthUser satisfies the BaseUser protocol
assert isinstance(AuthUser(identity="test"), BaseUser)


class AuthHandler:
    """Base class for authentication handlers."""

    async def authenticate(
        self,
        headers: dict[str, str],
        method: str = "",
        path: str = "",
    ) -> AuthUser | None:
        """Authenticate a request.

        Returns AuthUser if valid, None to reject.
        Raise an exception to return a specific error.
        """
        raise NotImplementedError
