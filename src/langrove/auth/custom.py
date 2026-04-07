"""Custom auth handler -- loads user-provided handler from langgraph.json.

Supports two modes:
1. Plain async function: ``async def handler(headers) -> dict``
2. ``langgraph_sdk.Auth`` instance with ``@auth.authenticate`` decorator
"""

from __future__ import annotations

import importlib.util
import inspect
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from langrove.auth.base import AuthHandler, AuthUser
from langrove.exceptions import AuthError, ConfigError


class CustomAuthHandler(AuthHandler):
    """Loads a user-provided auth handler from a module:attr spec.

    If the loaded attribute is a ``langgraph_sdk.Auth`` instance, extracts
    its ``@auth.authenticate`` handler and exposes the Auth instance via
    the ``auth`` property for downstream authorization.
    """

    def __init__(self, handler_spec: str, base_dir: Path | None = None):
        self._handler, self._auth_instance = self._load_handler(handler_spec, base_dir)
        self._handler_params = set(inspect.signature(self._handler).parameters)

    @property
    def auth(self) -> Any:
        """The ``langgraph_sdk.Auth`` instance, or None for plain function auth."""
        return self._auth_instance

    async def authenticate(
        self,
        headers: dict[str, str],
        method: str = "",
        path: str = "",
    ) -> AuthUser | None:
        try:
            # Build kwargs based on what the handler's signature accepts
            kwargs = self._build_kwargs(headers, method, path)
            result = await self._handler(**kwargs)
        except Exception as e:
            raise AuthError(str(e)) from e

        if result is None:
            return None

        # String result -> just identity
        if isinstance(result, str):
            return AuthUser(identity=result)

        if not isinstance(result, dict):
            # Object with identity property (MinimalUser protocol)
            if hasattr(result, "identity"):
                return AuthUser(
                    identity=result.identity,
                    display_name=getattr(result, "display_name", ""),
                    permissions=getattr(result, "permissions", ()),
                )
            raise AuthError("Auth handler must return a dict, string, or object with 'identity'")

        identity = result.get("identity")
        if not identity:
            raise AuthError("Auth handler must return 'identity' in result")

        return AuthUser(
            identity=str(identity),
            display_name=result.get("display_name", ""),
            permissions=result.get("permissions", ()),
            **{
                k: v
                for k, v in result.items()
                if k not in ("identity", "display_name", "permissions", "is_authenticated")
            },
        )

    def _build_kwargs(self, headers: dict[str, str], method: str, path: str) -> dict:
        """Build kwargs matching the handler's signature (SDK parameter injection)."""
        params = self._handler_params
        kwargs: dict[str, Any] = {}

        if "headers" in params:
            kwargs["headers"] = headers
        if "authorization" in params:
            kwargs["authorization"] = headers.get("authorization")
        if "method" in params:
            kwargs["method"] = method
        if "path" in params:
            kwargs["path"] = path

        # If the handler takes no recognized params, fall back to passing headers
        # (backwards compat with plain functions that just take headers)
        if not kwargs and params:
            # Plain function with a single positional param
            first_param = next(iter(params))
            if first_param not in ("self", "cls"):
                kwargs[first_param] = headers

        return kwargs

    @staticmethod
    def _load_handler(spec: str, base_dir: Path | None = None) -> tuple[Callable, Any]:
        """Load the handler from a module:attr spec.

        Returns (authenticate_fn, auth_instance_or_none).
        """
        if ":" not in spec:
            raise ConfigError(f"Invalid auth handler spec: '{spec}'. Expected 'module.py:handler'")

        module_path_str, attr_name = spec.rsplit(":", 1)
        base = base_dir or Path.cwd()
        module_path = (base / module_path_str).resolve()

        if not module_path.exists():
            raise ConfigError(f"Auth handler module not found: {module_path}")

        module_name = f"langrove_auth_{module_path.stem}"
        mod_spec = importlib.util.spec_from_file_location(module_name, module_path)
        if mod_spec is None or mod_spec.loader is None:
            raise ConfigError(f"Could not load auth module: {module_path}")

        module = importlib.util.module_from_spec(mod_spec)
        sys.modules[module_name] = module
        mod_spec.loader.exec_module(module)

        obj = getattr(module, attr_name, None)
        if obj is None:
            raise ConfigError(f"Auth handler '{attr_name}' not found in {module_path}")

        # Check if it's a langgraph_sdk.Auth instance
        try:
            from langgraph_sdk import Auth

            if isinstance(obj, Auth):
                fn = obj._authenticate_handler
                if fn is None:
                    raise ConfigError(
                        f"Auth instance '{attr_name}' has no @auth.authenticate handler"
                    )
                return fn, obj
        except ImportError:
            pass

        if not callable(obj):
            raise ConfigError(f"Auth handler '{attr_name}' is not callable")

        return obj, None
