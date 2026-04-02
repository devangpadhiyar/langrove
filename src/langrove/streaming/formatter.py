"""SSE formatter -- converts StreamParts to text/event-stream wire format.

This must match exactly what the LangGraph SDK's SSEDecoder expects:
  event: {event_type}
  data: {json_payload}

  (blank line separates events)
"""

from __future__ import annotations

from typing import Any

import orjson

from langrove.models.common import StreamPart


def _default(obj: Any) -> Any:
    """orjson fallback for types it can't serialize natively.

    LangChain message objects (HumanMessage, AIMessage, etc.) expose
    model_dump() / dict() -- use that. UUID and datetime are handled
    by orjson already, so this only fires for unknown types.
    """
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "dict"):
        return obj.dict()
    raise TypeError(f"Type is not JSON serializable: {type(obj).__name__}")


def _dumps(data: Any) -> str:
    return orjson.dumps(data, default=_default).decode()


def format_sse(part: StreamPart) -> str:
    """Format a StreamPart as an SSE message string.

    Returns a string like:
        event: values
        data: {"messages": [...]}

    """
    data = _dumps(part.data) if part.data is not None else "null"
    return f"event: {part.event}\ndata: {data}\n\n"


def format_sse_with_id(part: StreamPart, event_id: str) -> str:
    """Format with an event ID for reconnection support."""
    data = _dumps(part.data) if part.data is not None else "null"
    return f"event: {part.event}\nid: {event_id}\ndata: {data}\n\n"


def metadata_event(run_id: str) -> StreamPart:
    """Create the metadata event (always first in a stream)."""
    return StreamPart("metadata", {"run_id": run_id})


def end_event() -> StreamPart:
    """Create the end event (always last in a stream)."""
    return StreamPart("end", None)


def error_event(error: str, message: str = "") -> StreamPart:
    """Create an error event."""
    return StreamPart("error", {"error": error, "message": message})
