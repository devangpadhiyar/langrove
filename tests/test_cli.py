"""Tests for CLI .env loading."""

from __future__ import annotations

import json
import os
from pathlib import Path


class TestLoadDotenvFromConfig:
    """Unit tests for _load_dotenv_from_config helper."""

    def test_loads_env_file_from_config_dir(self, tmp_path: Path):
        from langrove.cli import _load_dotenv_from_config

        env_file = tmp_path / ".env"
        env_file.write_text("TEST_CLI_SENTINEL=hello_from_dotenv\n")

        config_file = tmp_path / "langgraph.json"
        config_file.write_text(json.dumps({"graphs": {}, "env": ".env"}))

        _load_dotenv_from_config(str(config_file))

        assert os.environ.get("TEST_CLI_SENTINEL") == "hello_from_dotenv"
        # Cleanup
        del os.environ["TEST_CLI_SENTINEL"]

    def test_loads_env_dict_from_config(self, tmp_path: Path):
        from langrove.cli import _load_dotenv_from_config

        config_file = tmp_path / "langgraph.json"
        config_file.write_text(
            json.dumps({"graphs": {}, "env": {"TEST_CLI_DICT_KEY": "dict_value"}})
        )

        _load_dotenv_from_config(str(config_file))

        assert os.environ.get("TEST_CLI_DICT_KEY") == "dict_value"
        del os.environ["TEST_CLI_DICT_KEY"]

    def test_silently_skips_missing_config(self, tmp_path: Path):
        from langrove.cli import _load_dotenv_from_config

        # Should not raise
        _load_dotenv_from_config(str(tmp_path / "nonexistent.json"))

    def test_silently_skips_invalid_json(self, tmp_path: Path):
        from langrove.cli import _load_dotenv_from_config

        bad_config = tmp_path / "langgraph.json"
        bad_config.write_text("not valid json")

        # Should not raise
        _load_dotenv_from_config(str(bad_config))

    def test_env_file_relative_to_config_dir_not_cwd(self, tmp_path: Path):
        from langrove.cli import _load_dotenv_from_config

        # Place config in a subdirectory, not cwd
        subdir = tmp_path / "project"
        subdir.mkdir()
        env_file = subdir / "custom.env"
        env_file.write_text("TEST_CLI_SUBDIR=subdir_value\n")

        config_file = subdir / "langgraph.json"
        config_file.write_text(json.dumps({"graphs": {}, "env": "custom.env"}))

        _load_dotenv_from_config(str(config_file))

        assert os.environ.get("TEST_CLI_SUBDIR") == "subdir_value"
        del os.environ["TEST_CLI_SUBDIR"]

    def test_missing_env_file_does_not_raise(self, tmp_path: Path):
        from langrove.cli import _load_dotenv_from_config

        config_file = tmp_path / "langgraph.json"
        config_file.write_text(json.dumps({"graphs": {}, "env": "missing.env"}))

        # Should not raise even if .env file is absent
        _load_dotenv_from_config(str(config_file))
