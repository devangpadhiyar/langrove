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


class TestMigrateCommand:
    """Tests for the `langrove migrate` CLI command."""

    def test_migrate_command_registered(self):
        from click.testing import CliRunner

        from langrove.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["migrate", "--help"])
        assert result.exit_code == 0
        assert (
            "migration" in result.output.lower()
            or "alembic" in result.output.lower()
            or "revision" in result.output.lower()
        )

    def test_migrate_exits_when_alembic_ini_missing(self, tmp_path: Path, monkeypatch):
        """migrate exits with code 1 when alembic.ini cannot be found."""
        from pathlib import Path as _Path

        from click.testing import CliRunner

        from langrove.cli import main

        # Patch Path.exists to always return False for alembic.ini lookups
        original_exists = _Path.exists

        def patched_exists(self):
            if "alembic.ini" in str(self):
                return False
            return original_exists(self)

        monkeypatch.setattr(_Path, "exists", patched_exists)

        runner = CliRunner()
        result = runner.invoke(main, ["migrate"])
        assert result.exit_code == 1
        assert "alembic.ini" in result.output

    def test_migrate_success(self, tmp_path: Path, monkeypatch):
        """migrate succeeds when alembic.ini exists and alembic.command.upgrade succeeds."""
        from pathlib import Path as _Path
        from unittest.mock import patch

        from click.testing import CliRunner

        from langrove.cli import main

        # Make alembic.ini appear to exist
        original_exists = _Path.exists

        def patched_exists(self):
            if "alembic.ini" in str(self):
                return True
            return original_exists(self)

        monkeypatch.setattr(_Path, "exists", patched_exists)

        with (
            patch("alembic.command.upgrade"),
            patch("alembic.config.Config.__init__", return_value=None),
            patch("alembic.config.Config.set_main_option"),
        ):
            runner = CliRunner()
            result = runner.invoke(main, ["migrate"])
            assert result.exit_code == 0
            assert "head" in result.output
