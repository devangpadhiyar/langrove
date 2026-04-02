"""Registry of loaded LangGraph graphs with schema extraction."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from langrove.exceptions import NotFoundError
from langrove.graph.loader import load_graph


class GraphInfo:
    """Metadata about a loaded graph."""

    __slots__ = ("graph_id", "graph", "input_schema", "output_schema", "state_schema", "config_schema")

    def __init__(self, graph_id: str, graph: Any):
        self.graph_id = graph_id
        self.graph = graph
        self.input_schema = self._extract_schema(graph, "get_input_schema")
        self.output_schema = self._extract_schema(graph, "get_output_schema")
        self.state_schema = self._extract_schema(graph, "get_state")
        self.config_schema = self._extract_schema(graph, "config_specs")

    @staticmethod
    def _extract_schema(graph: Any, method_name: str) -> dict[str, Any]:
        """Try to extract a JSON schema from the graph."""
        method = getattr(graph, method_name, None)
        if method is None:
            return {}
        try:
            result = method()
            if hasattr(result, "model_json_schema"):
                return result.model_json_schema()
            if hasattr(result, "schema"):
                return result.schema()
            return {}
        except Exception:
            return {}


class GraphRegistry:
    """Cache of loaded graphs, indexed by graph_id.

    Base graphs are stored without a checkpointer attached. Per-request
    copies are created via get_graph_for_request() with the checkpointer injected.
    """

    def __init__(self):
        self._graphs: dict[str, GraphInfo] = {}

    def load_from_config(self, graphs: dict[str, str], base_dir: Path | None = None) -> None:
        """Load all graphs from the config's graphs dict."""
        for graph_id, graph_spec in graphs.items():
            graph = load_graph(graph_spec, base_dir)
            self._graphs[graph_id] = GraphInfo(graph_id, graph)

    def get(self, graph_id: str) -> GraphInfo:
        """Get graph info by ID. Raises NotFoundError if not found."""
        info = self._graphs.get(graph_id)
        if info is None:
            raise NotFoundError("graph", graph_id)
        return info

    def get_graph_for_request(self, graph_id: str, checkpointer: Any, store: Any = None) -> Any:
        """Get a per-request copy of a graph with checkpointer injected.

        The base graph is immutable and shared. Each request gets its own copy
        with the checkpointer attached, and config deep-copied to prevent
        concurrent interference.
        """
        info = self.get(graph_id)
        base_graph = info.graph

        # Create a copy with injected checkpointer and store
        update = {"checkpointer": checkpointer}
        if store is not None:
            update["store"] = store

        # Deep copy config to prevent concurrent mutation
        if hasattr(base_graph, "config"):
            update["config"] = copy.deepcopy(base_graph.config)

        if hasattr(base_graph, "copy"):
            return base_graph.copy(update=update)

        # Fallback: set attributes directly (less safe but works)
        for key, value in update.items():
            setattr(base_graph, key, value)
        return base_graph

    def list_graphs(self) -> list[GraphInfo]:
        """Return all loaded graph infos."""
        return list(self._graphs.values())

    def __len__(self) -> int:
        return len(self._graphs)

    def __contains__(self, graph_id: str) -> bool:
        return graph_id in self._graphs
