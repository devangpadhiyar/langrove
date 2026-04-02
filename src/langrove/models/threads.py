"""Pydantic models for threads."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from langrove.models.common import Message


class Thread(BaseModel):
    """Thread response model."""

    thread_id: UUID
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any] = {}
    status: str = "idle"  # idle | busy | interrupted | error
    values: dict[str, Any] | None = None
    interrupts: list[Any] | None = None


class ThreadCreate(BaseModel):
    """Request body for creating a thread."""

    thread_id: UUID | None = None
    metadata: dict[str, Any] = {}
    if_exists: Literal["raise", "do_nothing"] = "raise"


class ThreadPatch(BaseModel):
    """Request body for updating a thread."""

    metadata: dict[str, Any] | None = None


class ThreadState(BaseModel):
    """Thread state at a checkpoint."""

    values: dict[str, Any] = {}
    next: list[str] = []
    checkpoint: dict[str, Any] = {}
    metadata: dict[str, Any] = {}
    tasks: list[dict[str, Any]] = []


class ThreadStateUpdate(BaseModel):
    """Request body for updating thread state."""

    values: dict[str, Any]
    as_node: str | None = None
    checkpoint_id: str | None = None


class ThreadSearchRequest(BaseModel):
    """Request body for searching threads."""

    metadata: dict[str, Any] | None = None
    status: str | None = None
    limit: int = Field(default=10, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class ThreadHistoryRequest(BaseModel):
    """Request body for thread history."""

    limit: int = Field(default=10, ge=1, le=100)
    before: str | None = None
    checkpoint_id: str | None = None
