# Langrove

Open-source, self-hosted drop-in replacement for LangGraph deployment (LangSmith Deployments).
Works with `langgraph_sdk.get_client()`, `useStream()` React hook, and Agent Chat UI.

## Architecture

- **API Server** (FastAPI/uvicorn): HTTP endpoints, SSE streaming for foreground runs
- **Worker Process**: Celery with celery-aio-pool (AsyncIOPool) for async task execution
- **PostgreSQL**: Threads, runs, assistants, store + LangGraph checkpoint tables
- **Redis**: Task queue (Celery broker), live stream relay (Pub/Sub), event replay

## Key Patterns

### Graph Instance Per Request
Base graphs cached at startup (no checkpointer). Per request: `graph.copy()` with injected checkpointer + `deepcopy(config)` to prevent concurrent interference.

### SSE Wire Format (useStream compatible)
```
event: metadata
data: {"run_id": "..."}

event: values
data: {state_dict}

event: end
data: null
```
Content-Type: text/event-stream. First event always `metadata`, last always `end`.

### Background Runs (Celery + Late-Ack)
1. API: `TaskPublisher.publish()` calls `handle_run.apply_async(kwargs=payload)` via thread pool
2. Celery worker picks up task from Redis queue (celery-aio-pool provides AsyncIOPool)
3. Worker: execute graph, publish events via Redis pub/sub
4. Worker: Celery ACKs only after task completes (`task_acks_late=True`)
5. On crash: `task_reject_on_worker_lost=True` re-queues the task
6. After max retries (default 3): dead-letter to `langrove:tasks:dead` Redis stream
7. Cancellation: API sets `langrove:runs:{run_id}:cancel` key + `app.control.revoke()`

### Thread State
Thread `values` and `interrupts` are NOT stored in the threads table. They are derived from the LangGraph checkpointer at read time.

## Project Structure

```
src/langrove/
  cli.py          - Click CLI (serve, worker, init)
  settings.py     - Pydantic BaseSettings
  config.py       - langgraph.json parser
  app.py          - FastAPI app factory
  exceptions.py   - Domain exceptions
  models/         - Pydantic DTOs
  db/             - asyncpg repositories (raw SQL)
  services/       - Business logic (one class per domain)
  graph/          - Graph loading + registry
  streaming/      - SSE executor, formatter, broker
  queue/          - Celery app (celery_app.py), task actors (tasks.py), publisher (publisher.py)
  auth/           - Auth handlers + middleware
  api/            - FastAPI route handlers (thin, delegate to services)
  worker.py       - Worker process main loop
```

## Common Commands

```bash
# Development
uv sync                              # Install dependencies
uv run langrove serve              # Start API server (port 8123)
uv run langrove worker             # Start background worker
docker compose up postgres redis     # Start infra only

# Testing
uv run pytest                        # Run all tests
uv run pytest tests/test_runs.py     # Run specific test file
uv run pytest -x -v                  # Stop on first failure, verbose

# Database
uv run alembic upgrade head          # Run migrations
uv run alembic revision -m "desc"    # Create new migration
```

## Principles

- KISS, YAGNI, SOLID, OOP
- No speculative abstractions -- add when a second implementation appears
- Flat structure where possible
- Raw asyncpg SQL, no ORM
- Services receive dependencies via constructor injection
- API handlers are thin -- delegate to services
