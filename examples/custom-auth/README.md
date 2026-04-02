# Custom Auth -- Securing Your Langrove Deployment

This example shows how to write and configure a custom authentication handler for Langrove.

## What You'll Learn

- How to write a custom async auth handler
- How to wire it into `langgraph.json` via `auth.path`
- How the auth middleware processes requests
- Which endpoints bypass auth (health, docs)
- How to pass auth headers via the `langgraph_sdk` client

## Project Structure

```
custom-auth/
  agent.py          # Simple chatbot graph
  auth.py           # Custom auth handler <-- the key file
  langgraph.json    # Config with auth.path set
  client.py         # SDK client demonstrating auth flows
  .env.example      # Environment variable template
```

## Setup

**1. Start infrastructure** (from the project root):

```bash
docker compose up postgres redis -d
uv run alembic upgrade head
```

**2. Configure environment:**

```bash
cd examples/custom-auth
cp .env.example .env
# Edit .env and set your OPENAI_API_KEY
```

**3. Start the server:**

```bash
uv run langrove serve
```

**4. Run the client:**

```bash
python client.py
```

## Auth Handler Interface

Your auth handler is an async function with this signature:

```python
async def authenticate(headers: dict[str, str]) -> dict:
    """
    Args:
        headers: HTTP request headers (lowercase keys).

    Returns:
        Dict with at least 'identity' key.
        Optional: 'role' (defaults to "user"), plus any extra metadata.

    Raises:
        Any exception -> 401 Unauthorized.
    """
```

### Return Value

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `identity` | Yes | -- | Unique user identifier (e.g., email, user ID) |
| `role` | No | `"user"` | Role string for access control |
| `**kwargs` | No | -- | Any extra fields stored as metadata |

### langgraph.json Configuration

```json
{
  "auth": {
    "path": "./auth.py:authenticate"
  }
}
```

The `path` format is `module_path:function_name`. Langrove dynamically imports the module and calls the function for each request.

## How the Middleware Works

1. Request arrives at Langrove
2. Auth middleware checks if the path is in the skip list (`/ok`, `/health`, `/info`, `/docs`, `/openapi.json`, `/redoc`)
3. If not skipped, calls your handler with the request headers
4. On success: creates `AuthUser(identity=..., role=..., **metadata)` and stores it in `request.state.user`
5. On failure (exception raised): returns `401 Unauthorized`

## Production Patterns

### JWT Validation

```python
import jwt

async def authenticate(headers: dict) -> dict:
    token = headers.get("authorization", "").removeprefix("Bearer ")
    payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    return {"identity": payload["sub"], "role": payload.get("role", "user")}
```

### Database API Key Lookup

```python
async def authenticate(headers: dict) -> dict:
    token = headers.get("x-api-key", "")
    # Query your database for the API key
    user = await db.fetch_one("SELECT * FROM api_keys WHERE key = $1", token)
    if not user:
        raise ValueError("Invalid API key")
    return {"identity": user["owner_id"], "role": user["role"]}
```

### External Identity Provider

```python
import httpx

async def authenticate(headers: dict) -> dict:
    token = headers.get("authorization", "").removeprefix("Bearer ")
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://auth.example.com/userinfo",
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
        userinfo = resp.json()
    return {"identity": userinfo["sub"], "role": userinfo.get("role", "user")}
```
