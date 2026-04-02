"""Custom auth handler -- loads user-provided handler from langgraph.json."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Callable

from langrove.auth.base import AuthHandler, AuthUser
from langrove.exceptions import AuthError, ConfigError


class CustomAuthHandler(AuthHandler):
    """Loads a user-provided auth handler function from a module:attr spec.

    The user's handler should be an async function that accepts headers (dict)
    and returns a dict with at least an 'identity' key, or raises an exception.

    Example user handler:
        async def my_auth(headers: dict) -> dict:
            token = headers.get("authorization", "").removeprefix("Bearer ")
            user = await verify_token(token)
            if not user:
                raise HTTPException(status_code=401)
            return {"identity": user.id, "role": user.role}
    """

    def __init__(self, handler_spec: str, base_dir: Path | None = None):
        self._handler = self._load_handler(handler_spec, base_dir)

    async def authenticate(self, headers: dict[str, str]) -> AuthUser | None:
        try:
            result = await self._handler(headers)
        except Exception as e:
            raise AuthError(str(e)) from e

        if result is None:
            return None

        if not isinstance(result, dict):
            raise AuthError("Auth handler must return a dict with 'identity' key")

        identity = result.get("identity")
        if not identity:
            raise AuthError("Auth handler must return 'identity' in result")

        return AuthUser(
            identity=str(identity),
            role=result.get("role", "user"),
            **{k: v for k, v in result.items() if k not in ("identity", "role")},
        )

    @staticmethod
    def _load_handler(spec: str, base_dir: Path | None = None) -> Callable:
        """Load the handler function from a module:attr spec."""
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

        handler = getattr(module, attr_name, None)
        if handler is None:
            raise ConfigError(f"Auth handler '{attr_name}' not found in {module_path}")

        if not callable(handler):
            raise ConfigError(f"Auth handler '{attr_name}' is not callable")

        return handler
