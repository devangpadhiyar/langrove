"""Pydantic models for crons."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class Cron(BaseModel):
    """Cron job response model."""

    cron_id: UUID
    assistant_id: UUID
    thread_id: UUID | None = None
    schedule: str
    payload: dict[str, Any] = {}
    metadata: dict[str, Any] = {}
    enabled: bool = True
    next_run_date: datetime | None = None
    created_at: datetime
    updated_at: datetime


class CronCreate(BaseModel):
    """Request body for creating a cron job."""

    assistant_id: str
    thread_id: UUID | None = None
    schedule: str
    payload: dict[str, Any] = {}
    metadata: dict[str, Any] = {}


class CronUpdate(BaseModel):
    """Request body for updating a cron job."""

    schedule: str | None = None
    payload: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    enabled: bool | None = None


class CronSearchRequest(BaseModel):
    """Request body for searching cron jobs."""

    assistant_id: UUID | None = None
    thread_id: UUID | None = None
    limit: int = Field(default=10, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)
