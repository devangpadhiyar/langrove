"""Shared models used across the application."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class Message(BaseModel):
    """Chat message (compatible with LangGraph SDK)."""

    role: str  # "user", "assistant", "system", "tool"
    content: str | list[Any]
    id: str | None = None
    metadata: dict[str, Any] = {}


class ErrorResponse(BaseModel):
    """Error response matching Agent Protocol spec."""

    code: str | None = None
    message: str | None = None
    metadata: dict[str, Any] = {}


class StreamPart:
    """A single SSE event to be sent to the client.

    Not a Pydantic model -- just a simple data container for internal use.
    """

    __slots__ = ("event", "data")

    def __init__(self, event: str, data: Any):
        self.event = event
        self.data = data
