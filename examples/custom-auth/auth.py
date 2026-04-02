"""Custom auth handler for Langrove.

Langrove calls this function for every incoming request (except health
endpoints like /ok, /health, /docs). The function receives the HTTP headers
and must return a dict with at least an ``identity`` key.

Interface:
    async def handler(headers: dict[str, str]) -> dict

Return dict fields:
    identity (str): Required. Unique user identifier.
    role (str):     Optional. Defaults to "user". Used for access control.
    **kwargs:       Any extra fields are stored as metadata on AuthUser.

Raise any exception to reject the request with 401.
"""

from __future__ import annotations

# API keys mapped to user identities and roles.
# In production, you'd validate JWTs, query a database, or call an
# identity provider instead.
API_KEYS: dict[str, dict] = {
    "sk-admin-key": {"identity": "admin@example.com", "role": "admin"},
    "sk-dev-key": {"identity": "developer@example.com", "role": "developer"},
    "sk-readonly-key": {"identity": "viewer@example.com", "role": "viewer"},
}


async def authenticate(headers: dict) -> dict:
    """Validate the Authorization header and return user info.

    Args:
        headers: HTTP request headers (lowercase keys).

    Returns:
        Dict with ``identity`` (required) and optional ``role`` + metadata.

    Raises:
        ValueError: If the token is missing or invalid.
    """
    auth_header = headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        raise ValueError("Missing or malformed Authorization header")

    token = auth_header.removeprefix("Bearer ").strip()
    user_info = API_KEYS.get(token)
    if user_info is None:
        raise ValueError("Invalid API key")

    return user_info
