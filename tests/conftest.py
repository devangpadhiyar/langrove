"""Shared test fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def fixtures_dir() -> Path:
    """Path to test fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def test_config_path(fixtures_dir: Path) -> str:
    """Path to test langgraph.json."""
    return str(fixtures_dir / "langgraph.json")
