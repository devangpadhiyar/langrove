"""Tests for configuration loading."""

from __future__ import annotations

from pathlib import Path

import pytest

from langrove.config import GraphConfig, load_config
from langrove.exceptions import ConfigError


class TestLoadConfig:
    def test_load_valid_config(self, test_config_path: str):
        config = load_config(test_config_path)
        assert "echo" in config.graphs
        assert config.graphs["echo"] == "./tests/fixtures/echo_graph.py:graph"

    def test_load_nonexistent_returns_defaults(self, tmp_path: Path):
        config = load_config(str(tmp_path / "nonexistent.json"))
        assert config.graphs == {}
        assert config.http.cors.allow_origins == ["*"]

    def test_load_invalid_json(self, tmp_path: Path):
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("not json")
        with pytest.raises(ConfigError, match="Invalid JSON"):
            load_config(str(bad_file))

    def test_load_invalid_graphs_type(self, tmp_path: Path):
        bad_file = tmp_path / "bad.json"
        bad_file.write_text('{"graphs": "not_a_dict"}')
        with pytest.raises(ConfigError, match="must be a dict"):
            load_config(str(bad_file))

    def test_cors_defaults(self):
        config = GraphConfig()
        assert config.http.cors.allow_origins == ["*"]
        assert config.http.cors.max_age == 600

    def test_auth_config(self, tmp_path: Path):
        config_file = tmp_path / "langgraph.json"
        config_file.write_text('{"graphs": {}, "auth": {"path": "./auth.py:handler"}}')
        config = load_config(str(config_file))
        assert config.auth.path == "./auth.py:handler"

    def test_http_config(self, tmp_path: Path):
        config_file = tmp_path / "langgraph.json"
        config_file.write_text(
            '{"graphs": {}, "http": {"disable_store": true, "cors": {"allow_origins": ["https://example.com"]}}}'
        )
        config = load_config(str(config_file))
        assert config.http.disable_store is True
        assert config.http.cors.allow_origins == ["https://example.com"]


class TestGraphLoading:
    def test_load_echo_graph(self, fixtures_dir: Path):
        from langrove.graph.loader import load_graph

        graph = load_graph("./tests/fixtures/echo_graph.py:graph", base_dir=Path.cwd())
        assert graph is not None
        assert hasattr(graph, "invoke") or hasattr(graph, "ainvoke")

    def test_load_nonexistent_module(self):
        from langrove.graph.loader import load_graph

        with pytest.raises(ConfigError, match="not found"):
            load_graph("./nonexistent.py:graph")

    def test_load_invalid_spec(self):
        from langrove.graph.loader import load_graph

        with pytest.raises(ConfigError, match="Invalid graph spec"):
            load_graph("no_colon_here")

    def test_load_nonexistent_attribute(self, fixtures_dir: Path):
        from langrove.graph.loader import load_graph

        with pytest.raises(ConfigError, match="not found"):
            load_graph("./tests/fixtures/echo_graph.py:nonexistent", base_dir=Path.cwd())


class TestGraphRegistry:
    def test_load_from_config(self, fixtures_dir: Path):
        from langrove.graph.registry import GraphRegistry

        registry = GraphRegistry()
        registry.load_from_config(
            {"echo": "./tests/fixtures/echo_graph.py:graph"},
            base_dir=Path.cwd(),
        )
        assert len(registry) == 1
        assert "echo" in registry

    def test_get_nonexistent_graph(self):
        from langrove.graph.registry import GraphRegistry
        from langrove.exceptions import NotFoundError

        registry = GraphRegistry()
        with pytest.raises(NotFoundError):
            registry.get("nonexistent")

    def test_list_graphs(self, fixtures_dir: Path):
        from langrove.graph.registry import GraphRegistry

        registry = GraphRegistry()
        registry.load_from_config(
            {"echo": "./tests/fixtures/echo_graph.py:graph"},
            base_dir=Path.cwd(),
        )
        graphs = registry.list_graphs()
        assert len(graphs) == 1
        assert graphs[0].graph_id == "echo"
