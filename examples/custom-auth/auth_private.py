"""Private conversations auth handler using langgraph_sdk.Auth.

This example demonstrates how to make threads and other resources
private to their creator using metadata-based filtering.

Usage in langgraph.json:
    {
      "graphs": {"agent": "./agent.py:graph"},
      "auth": {"path": "./auth_private.py:auth"}
    }
"""

from __future__ import annotations

from langgraph_sdk import Auth

auth = Auth()

# API keys mapped to user identities.
# In production, validate JWTs, query a database, or call an identity provider.
USERS: dict[str, Auth.types.MinimalUserDict] = {
    "sk-alice-key": {
        "identity": "alice@example.com",
        "display_name": "Alice",
        "permissions": ["read", "write"],
    },
    "sk-bob-key": {
        "identity": "bob@example.com",
        "display_name": "Bob",
        "permissions": ["read", "write"],
    },
    "sk-admin-key": {
        "identity": "admin@example.com",
        "display_name": "Admin",
        "permissions": ["read", "write", "admin"],
    },
}


@auth.authenticate
async def authenticate(authorization: str) -> Auth.types.MinimalUserDict:
    """Validate Bearer token and return user info."""
    token = (authorization or "").removeprefix("Bearer ").strip()
    user = USERS.get(token)
    if not user:
        raise Auth.exceptions.HTTPException(status_code=401, detail="Invalid API key")
    return user


@auth.on
async def add_owner(ctx: Auth.types.AuthContext, value: dict):
    """Global handler: make all resources private to their creator.

    On create: injects ``owner`` into metadata so the resource is tagged.
    On read/search/list: returns a filter so users only see their own resources.

    Result: Alice's threads are invisible to Bob, and vice versa.
    """
    filters = {"owner": ctx.user.identity}
    metadata = value.setdefault("metadata", {})
    metadata.update(filters)
    return filters
