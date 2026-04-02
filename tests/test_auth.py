"""Tests for authentication handlers."""

from __future__ import annotations

from pathlib import Path

import pytest

from langrove.auth.base import AuthUser
from langrove.auth.noop import NoopAuthHandler
from langrove.exceptions import ConfigError


class TestNoopAuth:
    @pytest.mark.asyncio
    async def test_always_authenticates(self):
        handler = NoopAuthHandler()
        user = await handler.authenticate({})
        assert isinstance(user, AuthUser)
        assert user.identity == "anonymous"
        assert user.role == "admin"


class TestCustomAuth:
    def test_load_invalid_spec(self):
        from langrove.auth.custom import CustomAuthHandler

        with pytest.raises(ConfigError, match="Invalid auth handler spec"):
            CustomAuthHandler("no_colon")

    def test_load_nonexistent_module(self):
        from langrove.auth.custom import CustomAuthHandler

        with pytest.raises(ConfigError, match="not found"):
            CustomAuthHandler("./nonexistent.py:handler")

    @pytest.mark.asyncio
    async def test_load_and_call_handler(self, tmp_path: Path):
        # Create a test auth handler
        handler_file = tmp_path / "test_auth.py"
        handler_file.write_text(
            "async def handler(headers):\n"
            "    token = headers.get('authorization', '')\n"
            "    if token == 'Bearer valid':\n"
            "        return {'identity': 'user-1', 'role': 'admin'}\n"
            "    return None\n"
        )

        from langrove.auth.custom import CustomAuthHandler

        auth = CustomAuthHandler(f"{handler_file}:handler", base_dir=tmp_path)

        # Valid token
        user = await auth.authenticate({"authorization": "Bearer valid"})
        assert user is not None
        assert user.identity == "user-1"
        assert user.role == "admin"

        # Invalid token
        user = await auth.authenticate({"authorization": "Bearer invalid"})
        assert user is None
