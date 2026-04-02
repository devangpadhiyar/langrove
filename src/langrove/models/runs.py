"""Pydantic models for runs."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from langrove.models.common import Message


class Run(BaseModel):
    """Run response model."""

    run_id: UUID
    thread_id: UUID | None = None
    assistant_id: UUID | None = None
    status: str = "pending"  # pending | running | success | error | timeout | interrupted
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any] = {}
    kwargs: dict[str, Any] = {}
    multitask_strategy: str = "reject"


class RunCreate(BaseModel):
    """Request body for creating a run."""

    assistant_id: str | None = None
    input: Any | None = None
    command: dict[str, Any] | None = None
    messages: list[Message] | None = None
    metadata: dict[str, Any] = {}
    config: dict[str, Any] | None = None
    webhook: str | None = None
    stream_mode: str | list[str] | None = None
    stream_subgraphs: bool = False
    on_completion: Literal["delete", "keep"] = "keep"
    on_disconnect: Literal["cancel", "continue"] = "cancel"
    if_not_exists: Literal["create", "reject"] = "reject"
    multitask_strategy: Literal["reject", "interrupt", "rollback", "enqueue"] = "reject"
    interrupt_before: list[str] | None = None
    interrupt_after: list[str] | None = None
    checkpoint_id: str | None = None
    after_seconds: float | None = None


class RunWaitResponse(BaseModel):
    """Response for /runs/wait endpoints."""

    values: dict[str, Any] = {}
    messages: list[Message] = []


class RunSearchRequest(BaseModel):
    """Request body for searching runs."""

    thread_id: UUID | None = None
    assistant_id: UUID | None = None
    status: str | None = None
    metadata: dict[str, Any] | None = None
    limit: int = Field(default=10, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)
