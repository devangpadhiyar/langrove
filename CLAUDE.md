# Langrove

Open-source, self-hosted drop-in replacement for LangGraph deployment (LangSmith Deployments).
Works with `langgraph_sdk.get_client()`, `useStream()` React hook, and Agent Chat UI.

## Architecture

- **API Server** (FastAPI/uvicorn): HTTP endpoints, SSE streaming for foreground runs
- **Worker Process**: Consumes background tasks via Dramatiq (RedisBroker), executes LangGraph graphs
- **PostgreSQL**: Threads, runs, assistants, store + LangGraph checkpoint tables
- **Redis**: Task queue (Dramatiq RedisBroker — RPOPLPUSH late-ack), live stream relay (Pub/Sub), event replay

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

### Background Runs (Dramatiq + Late-Ack)
1. API: `TaskPublisher.publish()` → `asyncio.to_thread(handle_run.send_with_options, kwargs=payload)`
2. Dramatiq `RedisBroker` atomically moves message from queue → processing list (RPOPLPUSH)
3. Worker `handle_run` actor executes graph, publishes events via Redis pub/sub
4. Actor returns cleanly → Dramatiq deletes from processing list (ACK)
5. On crash: message stays in processing list; Dramatiq requeue thread reclaims it
6. After `max_retries` failures: `DeadLetterMiddleware` writes to `langrove:tasks:dead` stream
7. Run cancellation: API sets `langrove:runs:{run_id}:cancel` key; actor polls after each event

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
  queue/          - Dramatiq broker setup (broker.py), task actors (tasks.py), publisher (publisher.py)
  auth/           - Auth handlers + middleware
  api/            - FastAPI route handlers (thin, delegate to services)
  worker.py       - Worker process main loop
```

## Common Commands

```bash
# Development
uv sync                              # Install dependencies
uv run langrove serve              # Start API server (port 8123)
uv run langrove worker             # Start background worker (all queues, 5 threads)
docker compose up postgres redis     # Start infra only

# Worker — Dramatiq-native flags
uv run langrove worker -Q langrove               # Listen on specific queue
uv run langrove worker -t 10                     # 10 worker threads (--concurrency)
uv run langrove worker --max-retries 5           # 5 attempts before dead-letter
uv run langrove worker --worker-timeout 1000     # Idle-poll interval 1 s (ms)
uv run langrove worker --worker-id worker-1 -t 10 --shutdown-timeout 60

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
