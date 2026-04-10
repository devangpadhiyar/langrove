"""Pydantic models for the store."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class Item(BaseModel):
    """Store item response model."""

    namespace: list[str]
    key: str
    value: Any
    created_at: datetime | None = None
    updated_at: datetime | None = None


class StorePutRequest(BaseModel):
    """Request body for upserting a store item."""

    namespace: list[str]
    key: str
    value: Any


class StoreDeleteRequest(BaseModel):
    """Request body for deleting a store item."""

    namespace: list[str]
    key: str


class StoreSearchRequest(BaseModel):
    """Request body for searching store items."""

    namespace_prefix: list[str] | None = None
    filter: dict[str, Any] | None = None
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class StoreListNamespacesRequest(BaseModel):
    """Request body for listing store namespaces."""

    prefix: list[str] | None = None
    suffix: list[str] | None = None
    max_depth: int | None = None
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class NamespaceInfo(BaseModel):
    """Namespace info response."""

    path: list[str]
