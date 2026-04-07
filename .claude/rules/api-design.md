---
description: FastAPI route patterns, dependency injection, service layer, error handling, and request/response models
globs:
  - "src/langrove/api/**/*.py"
  - "src/langrove/models/**/*.py"
  - "src/langrove/services/**/*.py"
  - "src/langrove/exceptions.py"
---

# API Design

## Route Handler Pattern
- **Thin handlers** — delegate ALL business logic to services
- Handlers only: parse request, inject dependencies, call service, return response
- One router per resource: agents, assistants, threads, runs, store, crons, health, dead_letter

## Dependency Injection
- FastAPI `Depends()` functions in `api/deps.py`
- App-level resources: `request.app.state.{db_pool, redis, graph_registry, checkpointer, store}`
- Request-scoped: `request.state.{user, auth}`
- Service factory pattern:
  ```python
  def _get_service(db=Depends(get_db), registry=Depends(get_graph_registry)):
      return ServiceClass(Repository(db), registry)
  ```

## Service Layer
- Services instantiated fresh per-request (not cached)
- Constructor injection: `__init__(self, repo, registry, ...)`
- Repositories are lightweight, stateless data-access objects
- One service per domain: AssistantService, RunService, ThreadService, StoreService, CronService

## Error Hierarchy
```
LangroveError (base)
├── NotFoundError(resource: str, resource_id: str) → 404
├── ConflictError(message: str) → 409
├── AuthError(message: str) → 401
└── ForbiddenError(message: str) → 403
```
- Response format: `JSONResponse({"code": "error_type", "message": "..."})`
- Exception handlers registered in `app.py`

## Request/Response Models
- Response models: Pydantic `BaseModel` with UUID + datetime fields
- Create models: optional `if_exists` field ("raise" | "do_nothing")
- Search models: optional filters + `limit`/`offset` pagination
- Patch/Update: all fields optional, `model_dump(exclude_none=True)` for partial updates

## Key Patterns
- `if_exists="do_nothing"` returns existing record instead of ConflictError
- Thread state is dual-sourced: record (metadata, status) from repo + state (values, next, tasks) from checkpointer
- Ephemeral threads: auto-deleted after stream completes if `on_completion="delete"`
- Run cancellation: DB status → "interrupted" + Redis cancel key + thread reset to "idle"

## Three Run Execution Modes
1. `stream_run()` — foreground SSE streaming (same process, asyncio.Queue)
2. `wait_run()` — foreground blocking, returns final state
3. `background_run()` — dispatches to Redis Streams queue, returns Run immediately

## Gotchas
- Services are NOT singletons — new instance per request
- `metadata_` → `metadata` rename happens in repository layer, not service/API layer
- Auth user injected into graph config as `langgraph_auth_user` key in configurable dict
