"""Pydantic models for assistants and agents."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class Assistant(BaseModel):
    """Assistant response model."""

    assistant_id: UUID
    graph_id: str
    name: str = ""
    description: str | None = None
    config: dict[str, Any] = {}
    metadata: dict[str, Any] = {}
    version: int = 1
    created_at: datetime
    updated_at: datetime


class AssistantCreate(BaseModel):
    """Request body for creating an assistant."""

    assistant_id: UUID | None = None
    graph_id: str
    name: str = ""
    description: str | None = None
    config: dict[str, Any] = {}
    metadata: dict[str, Any] = {}
    if_exists: str = "raise"  # "raise" | "do_nothing"


class AssistantUpdate(BaseModel):
    """Request body for updating an assistant."""

    name: str | None = None
    description: str | None = None
    graph_id: str | None = None
    config: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


class AssistantSearchRequest(BaseModel):
    """Request body for searching assistants."""

    name: str | None = None
    graph_id: str | None = None
    metadata: dict[str, Any] | None = None
    limit: int = Field(default=10, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


# Agent Protocol models (thin wrappers)

class Agent(BaseModel):
    """Agent Protocol agent model."""

    agent_id: str
    name: str
    description: str | None = None
    metadata: dict[str, Any] = {}
    capabilities: dict[str, Any] = {}


class AgentSchemas(BaseModel):
    """Agent Protocol schemas response."""

    agent_id: str
    input_schema: dict[str, Any] = {}
    output_schema: dict[str, Any] = {}
    state_schema: dict[str, Any] | None = None
    config_schema: dict[str, Any] | None = None
