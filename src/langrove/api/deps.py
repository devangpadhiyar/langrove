"""FastAPI dependency injection helpers."""

from __future__ import annotations

from typing import Any

from fastapi import Request

from langrove.db.pool import DatabasePool
from langrove.graph.registry import GraphRegistry


def get_db(request: Request) -> DatabasePool:
    """Get the database pool from app state."""
    return request.app.state.db_pool


def get_redis(request: Request) -> Any:
    """Get the Redis client from app state."""
    return request.app.state.redis


def get_graph_registry(request: Request) -> GraphRegistry:
    """Get the graph registry from app state."""
    return request.app.state.graph_registry


def get_checkpointer(request: Request) -> Any:
    """Get the LangGraph checkpointer from app state."""
    return request.app.state.checkpointer
