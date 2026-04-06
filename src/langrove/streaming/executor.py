"""Graph execution engine -- ported from Aegra's graph_streaming approach.

Uses astream() with message accumulation, emitting messages/metadata +
messages/partial per chunk so the SDK useStream hook gets real-time tokens.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import aclosing
from typing import Any, cast

from langchain_core.messages import BaseMessage

from langrove.graph.registry import GraphRegistry
from langrove.models.common import StreamPart

logger = logging.getLogger(__name__)


def _process_stream_event(
    mode: str,
    chunk: Any,
    stream_mode: list[str],
    only_interrupt_updates: bool,
    values_explicit: bool = True,
) -> list[StreamPart]:
    """Convert one (mode, chunk) pair into StreamParts.

    Mirrors Aegra's _process_stream_event:
    - messages mode: accumulate chunks by ID, emit messages/metadata once then
      messages/partial (chunk) or messages/complete (full message) each time.
    - Other requested modes: pass through as-is.
    - updates mode (implicit): only forward if contains __interrupt__ data.
    """
    results: list[StreamPart] = []

    if mode == "messages":
        # chunk is (BaseMessageChunk, metadata_dict) from LangGraph astream
        msg, meta = cast("tuple[BaseMessage | dict, dict[str, Any]]", chunk)

        # Serialize to dict — SDK accumulates chunks itself
        msg_dict = msg.model_dump() if hasattr(msg, "model_dump") else msg

        # SDK expects: event "messages", data [messageDict, metadata]
        results.append(StreamPart("messages", [msg_dict, meta]))

    elif mode == "values" and not values_explicit:
        # values was added implicitly — suppress to avoid SDK treating history as complete state
        pass

    elif mode in stream_mode:
        results.append(StreamPart(mode, chunk))

    elif mode == "updates" and only_interrupt_updates:
        has_interrupt = (
            isinstance(chunk, dict)
            and "__interrupt__" in chunk
            and len(chunk.get("__interrupt__", [])) > 0
        )
        if has_interrupt:
            results.append(StreamPart("values", chunk))

    return results


class RunExecutor:
    """Executes LangGraph graphs and yields StreamPart events."""

    def __init__(self, registry: GraphRegistry, checkpointer: Any, store: Any = None):
        self._registry = registry
        self._checkpointer = checkpointer
        self._store = store

    async def execute_stream(
        self,
        graph_id: str,
        *,
        input: Any | None = None,
        command: dict[str, Any] | None = None,
        config: dict[str, Any] | None = None,
        thread_id: str | None = None,
        stream_mode: str | list[str] = "values",
        stream_subgraphs: bool = False,
        interrupt_before: list[str] | None = None,
        interrupt_after: list[str] | None = None,
        checkpoint_id: str | None = None,
    ) -> AsyncIterator[StreamPart]:
        """Execute a graph and yield StreamPart events."""
        graph = self._registry.get_graph_for_request(
            graph_id, self._checkpointer, store=self._store
        )

        # Build runnable config
        configurable: dict[str, Any] = {}
        if thread_id:
            configurable["thread_id"] = thread_id
        if checkpoint_id:
            configurable["checkpoint_id"] = checkpoint_id
        if config and "configurable" in config:
            configurable.update(config["configurable"])

        runnable_config: dict[str, Any] = {"configurable": configurable}
        if config:
            for key in ("recursion_limit", "tags", "metadata"):
                if key in config:
                    runnable_config[key] = config[key]

        # Determine input
        input_or_command = input
        if command:
            try:
                from langgraph.types import Command

                input_or_command = Command(**command)
            except (ImportError, Exception):
                input_or_command = input

        # Normalize stream_mode to list
        modes: list[str] = [stream_mode] if isinstance(stream_mode, str) else list(stream_mode)

        # Always include updates for interrupt detection (Aegra pattern)
        modes_set: set[str] = set(modes) - {"events", "messages-tuple"}
        updates_explicit = "updates" in modes_set
        values_explicit = "values" in modes_set
        if not updates_explicit:
            modes_set.add("updates")
        only_interrupt_updates = not updates_explicit

        # Convert messages-tuple -> messages for Python graphs (SDK adds it automatically)
        has_messages = "messages" in modes or "messages-tuple" in modes
        if has_messages:
            modes_set.add("messages")

        # Strip SDK-internal modes from the user-requested list used for pass-through checks
        modes = [m for m in modes if m not in ("messages-tuple", "events")]

        try:
            async with aclosing(
                graph.astream(
                    input_or_command,
                    config=runnable_config,
                    stream_mode=list(modes_set),
                    subgraphs=stream_subgraphs,
                    interrupt_before=interrupt_before,
                    interrupt_after=interrupt_after,
                )
            ) as stream:
                async for event in stream:
                    # Multi-mode astream yields (mode, chunk) tuples
                    if isinstance(event, tuple) and len(event) == 2:
                        mode, chunk = cast("tuple[str, Any]", event)
                    else:
                        mode = modes[0] if modes else "values"
                        chunk = event

                    for part in _process_stream_event(
                        mode=mode,
                        chunk=chunk,
                        stream_mode=modes,
                        only_interrupt_updates=only_interrupt_updates,
                        values_explicit=values_explicit,
                    ):
                        yield part

        except Exception as e:
            logger.exception("Error during graph execution for %s", graph_id)
            yield StreamPart("error", {"error": str(e), "message": type(e).__name__})

    async def execute_wait(
        self,
        graph_id: str,
        *,
        input: Any | None = None,
        command: dict[str, Any] | None = None,
        config: dict[str, Any] | None = None,
        thread_id: str | None = None,
        interrupt_before: list[str] | None = None,
        interrupt_after: list[str] | None = None,
        checkpoint_id: str | None = None,
    ) -> dict[str, Any]:
        """Execute a graph and return the final state (blocking)."""
        graph = self._registry.get_graph_for_request(
            graph_id, self._checkpointer, store=self._store
        )

        configurable: dict[str, Any] = {}
        if thread_id:
            configurable["thread_id"] = thread_id
        if checkpoint_id:
            configurable["checkpoint_id"] = checkpoint_id
        if config and "configurable" in config:
            configurable.update(config["configurable"])

        runnable_config: dict[str, Any] = {"configurable": configurable}
        if config:
            for key in ("recursion_limit", "tags", "metadata"):
                if key in config:
                    runnable_config[key] = config[key]

        input_or_command = input
        if command:
            try:
                from langgraph.types import Command

                input_or_command = Command(**command)
            except (ImportError, Exception):
                input_or_command = input

        result = await graph.ainvoke(
            input_or_command,
            config=runnable_config,
            interrupt_before=interrupt_before,
            interrupt_after=interrupt_after,
        )
        return result if isinstance(result, dict) else {"result": result}
