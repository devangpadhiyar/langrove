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


def get_store(request: Request) -> Any:
    """Get the LangGraph store from app state."""
    return getattr(request.app.state, "store", None)


def get_task_broker(request: Request) -> Any:
    """Get the Taskiq task broker from app state."""
    return request.app.state.task_broker


def get_auth_user(request: Request) -> Any:
    """Get the authenticated user from request state, or None."""
    return getattr(request.state, "user", None)


async def authorize(request: Request, resource: str, action: str, value: dict) -> dict:
    """Run the authorization handler for a resource+action.

    Resolves the most specific handler registered on the ``langgraph_sdk.Auth``
    instance and calls it with an ``AuthContext`` and the mutable ``value`` dict.

    Returns the (possibly modified) value dict, or a filter dict for searches.
    Raises ``ForbiddenError`` if the handler returns ``False``.

    When no Auth instance is configured (plain function auth or no auth),
    this is a no-op passthrough.
    """
    auth_instance = getattr(request.state, "auth", None)
    user = getattr(request.state, "user", None)
    if auth_instance is None or user is None:
        return value

    handler = _resolve_handler(auth_instance, resource, action)
    if handler is None:
        return value

    from langgraph_sdk.auth.types import AuthContext

    ctx = AuthContext(
        user=user,
        resource=resource,
        action=action,
        permissions=getattr(user, "permissions", ()),
    )
    result = await handler(ctx=ctx, value=value)

    if result is False:
        from langrove.exceptions import ForbiddenError

        raise ForbiddenError(f"Not authorized to {action} {resource}")

    if result is None or result is True:
        return value

    if isinstance(result, dict):
        return result

    return value


async def authorize_read(request: Request, resource: str, resource_metadata: dict | None) -> None:
    """Validate that a fetched resource passes authorization filters.

    Calls the authorization handler for ``(resource, "read")`` and checks
    that the returned filter matches the resource's metadata. Raises
    ``ForbiddenError`` if the metadata doesn't satisfy the filter.
    """
    auth_instance = getattr(request.state, "auth", None)
    user = getattr(request.state, "user", None)
    if auth_instance is None or user is None:
        return

    handler = _resolve_handler(auth_instance, resource, "read")
    if handler is None:
        return

    from langgraph_sdk.auth.types import AuthContext

    ctx = AuthContext(
        user=user,
        resource=resource,
        action="read",
        permissions=getattr(user, "permissions", ()),
    )
    result = await handler(ctx=ctx, value={})

    if result is False:
        from langrove.exceptions import ForbiddenError

        raise ForbiddenError(f"Not authorized to read {resource}")

    if isinstance(result, dict) and resource_metadata is not None:
        # Check that the resource metadata satisfies the filter
        for key, expected in result.items():
            actual = resource_metadata.get(key)
            if isinstance(expected, dict):
                # $eq or $contains operators
                if "$eq" in expected and actual != expected["$eq"]:
                    from langrove.exceptions import ForbiddenError

                    raise ForbiddenError(f"Not authorized to read {resource}")
                if "$contains" in expected:
                    contains_val = expected["$contains"]
                    if isinstance(contains_val, list):
                        if not isinstance(actual, list) or not all(
                            v in actual for v in contains_val
                        ):
                            from langrove.exceptions import ForbiddenError

                            raise ForbiddenError(f"Not authorized to read {resource}")
                    elif actual != contains_val and (
                        not isinstance(actual, list) or contains_val not in actual
                    ):
                        from langrove.exceptions import ForbiddenError

                        raise ForbiddenError(f"Not authorized to read {resource}")
            elif actual != expected:
                from langrove.exceptions import ForbiddenError

                raise ForbiddenError(f"Not authorized to read {resource}")


def _resolve_handler(auth: Any, resource: str, action: str) -> Any:
    """Resolve the most specific authorization handler.

    Priority: exact (resource, action) > resource-level (resource, *) > global.
    """
    # Exact match
    handlers = getattr(auth, "_handlers", {})
    if (resource, action) in handlers:
        return handlers[(resource, action)][0]
    # Resource-level
    if (resource, "*") in handlers:
        return handlers[(resource, "*")][0]
    # Global
    global_handlers = getattr(auth, "_global_handlers", [])
    if global_handlers:
        return global_handlers[0]
    return None
