"""Dynamically load LangGraph compiled graphs from module:attr specifications."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

from langrove.exceptions import ConfigError


def load_graph(graph_spec: str, base_dir: Path | None = None) -> Any:
    """Load a compiled graph from a 'path/to/module.py:attribute' spec.

    Args:
        graph_spec: e.g. "./my_agent/agent.py:graph"
        base_dir: Directory to resolve relative paths against. Defaults to cwd.

    Returns:
        The compiled LangGraph graph object.
    """
    if ":" not in graph_spec:
        raise ConfigError(
            f"Invalid graph spec '{graph_spec}'. Expected format: './module.py:attribute'"
        )

    module_path_str, attribute = graph_spec.rsplit(":", 1)
    base = base_dir or Path.cwd()
    module_path = (base / module_path_str).resolve()

    if not module_path.exists():
        raise ConfigError(f"Graph module not found: {module_path}")

    # Add parent directory to sys.path for imports
    parent_dir = str(module_path.parent)
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)

    # Dynamic import
    module_name = f"langrove_graph_{module_path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ConfigError(f"Could not load module spec from: {module_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    graph = getattr(module, attribute, None)
    if graph is None:
        raise ConfigError(f"Attribute '{attribute}' not found in module '{module_path}'")

    return graph
