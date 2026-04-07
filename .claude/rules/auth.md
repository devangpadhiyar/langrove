---
description: Authentication middleware, authorization handlers, AuthUser protocol, and custom auth loading
globs:
  - "src/langrove/auth/**/*.py"
---

# Authentication & Authorization

## Two-Stage Auth
1. **Authenticate** (request-level via middleware): validates credentials → returns AuthUser
2. **Authorize** (per-operation via deps.py): checks if user can perform action on resource

## Auth Handler Resolution (Priority Order)
1. Exact match: `(resource, action)` — e.g., `("assistants", "create")`
2. Resource-level: `(resource, *)` — e.g., `("assistants", "*")`
3. Global: catches all

## AuthUser Protocol
- Implements `langgraph_sdk.auth.types.BaseUser`
- Properties: `identity`, `display_name`, `permissions`, `is_authenticated`
- Dict-like access: `user[key]`, `key in user`, `iter(user)`
- `to_dict()` serializes for graph configurable injection as `langgraph_auth_user`
- Uses `__slots__` for memory efficiency

## CustomAuthHandler (auth/custom.py)
- Loads from `module.py:handler` spec in `langgraph.json` auth config
- Supports two modes:
  - Plain async function: `async def handler(headers) -> dict`
  - `langgraph_sdk.Auth` instance with `@auth.authenticate` decorator

### Parameter Injection (signature-based)
Handler parameters are inspected and injected:
- `headers` → full headers dict
- `authorization` → extracted from `headers["authorization"]`
- `method` → HTTP method string
- `path` → request path string
- Unknown params → falls back to headers as first positional arg

### Return Type Handling
- `None` → 401 (reject)
- `str` → `AuthUser(identity=string)`
- `dict` → must have `identity` key, optional `display_name`, `permissions`
- Object with `.identity` → extracted as MinimalUser protocol

## AuthMiddleware (auth/middleware.py)
- Extends `BaseHTTPMiddleware`
- Skip paths: `/ok`, `/health`, `/info`, `/docs`, `/openapi.json`, `/redoc`
- Skips OPTIONS (CORS preflight)
- Stores result: `request.state.user` (AuthUser) + `request.state.auth` (langgraph_sdk.Auth or None)

## Authorization in API Endpoints (deps.py)
- `authorize(request, resource, action, value_dict)` — for write operations
  - Handler can return `False` (reject → 403), `True/None` (accept), or modified dict (rewrite values)
- `authorize_read(request, resource, metadata)` — for read operations
  - Validates fetched resource against filter operators: `$eq`, `$contains`

## NoopAuthHandler (auth/noop.py)
- Development mode: always returns `AuthUser(identity="anonymous", permissions=("authenticated",))`

## Gotchas
- Auth is null-safe: no `request.state.auth` = no-op passthrough
- `request.state.auth` is the `langgraph_sdk.Auth` instance (for authorization rules), not the AuthUser
- Store namespace can be rewritten by auth handler via authorization result
