# Langrove

Open-source, self-hosted drop-in replacement for LangGraph deployment (LangSmith Deployments).

Works with `langgraph_sdk.get_client()`, the `useStream()` React hook, and [Agent Chat UI](https://github.com/langchain-ai/agent-chat-ui). Agent Protocol compliant.

## Why Langrove?

LangGraph Cloud is proprietary and requires LangSmith. Langrove gives you the same API surface — assistants, threads, runs, streaming, store, crons — on your own infrastructure. Deploy anywhere: bare metal, Docker, Kubernetes.

## Features

- **Full LangGraph SDK compatibility** — `get_client()` works out of the box
- **SSE streaming** — `useStream()` compatible wire format (messages, values, updates)
- **Background runs** — Dramatiq + Redis with at-least-once delivery, crash recovery, dead-letter queue
- **Persistent threads** — PostgreSQL-backed checkpointing with state history
- **Cross-thread store** — Hierarchical key-value storage with namespace search
- **Cron jobs** — Schedule recurring graph executions
- **Interrupt/resume** — Pause graphs at any node, resume with human input
- **Multitask strategies** — reject, interrupt, rollback, enqueue
- **Custom auth** — Plug in JWT, API key, or any async auth handler
- **Agent Protocol** — `/agents` endpoints for standard agent interop
- **AI-assisted development** — Automated planning, implementation, review, and merge via Claude Code

## Quickstart

```bash
# 1. Install
uv sync

# 2. Start infrastructure
docker compose up postgres redis -d

# 3. Run migrations
uv run alembic upgrade head

# 4. Initialize a project (creates langgraph.json + agent.py)
uv run langrove init

# 5. Start the server
uv run langrove serve

# 6. Start the background worker (separate terminal)
uv run langrove worker
```

The API is now running at `http://localhost:8123`. Use any LangGraph SDK client:

```python
from langgraph_sdk import get_client

client = get_client(url="http://localhost:8123")

# Create a thread and stream a response
thread = await client.threads.create()
async for event in client.runs.stream(
    thread["thread_id"],
    "agent",  # graph_id from langgraph.json
    input={"messages": [{"role": "user", "content": "Hello!"}]},
):
    print(event)
```

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│   Client     │────▶│  API Server  │────▶│  PostgreSQL  │
│  (SDK/UI)    │◀────│  (FastAPI)   │     │  (threads,   │
└─────────────┘ SSE └──────┬───────┘     │  runs, store,│
                           │             │  checkpoints)│
                           ▼             └──────────────┘
                    ┌──────────────┐
                    │    Redis     │
                    │  (Dramatiq   │
                    │   queue +    │
                    │   Pub/Sub)   │
                    └──────┬───────┘
                           │
                           ▼
                    ┌──────────────┐
                    │   Worker     │
                    │  (Dramatiq   │
                    │   actor,     │
                    │   graph exec)│
                    └──────────────┘
```

- **API Server** (FastAPI/uvicorn) — HTTP endpoints, SSE streaming for foreground runs
- **Worker** — Dramatiq actor (`handle_run`) consumes the `langrove` queue, executes LangGraph graphs
- **PostgreSQL** — Threads, runs, assistants, store, crons + LangGraph checkpoint tables
- **Redis** — Dramatiq `RedisBroker` (RPOPLPUSH late-ack), live stream relay (Pub/Sub), event replay

## Configuration

### langgraph.json

```json
{
  "graphs": {
    "agent": "./agent.py:graph"
  },
  "auth": {
    "path": "./auth.py:authenticate",
    "type": "custom"
  },
  "http": {
    "cors": {
      "allow_origins": ["http://localhost:3000"],
      "allow_methods": ["*"],
      "allow_headers": ["*"],
      "allow_credentials": true
    }
  }
}
```

### Environment Variables

All variables use the `LANGROVE_` prefix.

| Variable | Default | Description |
|----------|---------|-------------|
| `LANGROVE_DATABASE_URL` | `postgresql://langrove:langrove@localhost:5432/langrove` | PostgreSQL connection string |
| `LANGROVE_REDIS_URL` | `redis://localhost:6379` | Redis connection string |
| `LANGROVE_HOST` | `0.0.0.0` | API server bind address |
| `LANGROVE_PORT` | `8123` | API server port |
| `LANGROVE_CONFIG_PATH` | `langgraph.json` | Path to config file |
| `LANGROVE_WORKER_CONCURRENCY` | `5` | Worker thread count (tasks processed in parallel) |
| `LANGROVE_WORKER_TIMEOUT_MS` | `5000` | Idle-poll interval — ms a thread waits for a new message |
| `LANGROVE_TASK_TIMEOUT_SECONDS` | `900` | Max execution time per task (killed by Dramatiq `TimeLimit`) |
| `LANGROVE_MAX_DELIVERY_ATTEMPTS` | `3` | Retry attempts before message is dead-lettered |
| `LANGROVE_SHUTDOWN_TIMEOUT_SECONDS` | `30` | Graceful drain window before force-stop on SIGTERM |
| `LANGROVE_DB_POOL_MIN_SIZE` | `2` | asyncpg min pool connections |
| `LANGROVE_DB_POOL_MAX_SIZE` | `10` | asyncpg max pool connections |
| `LANGROVE_EVENT_STREAM_TTL_SECONDS` | `86400` | How long background run events are kept in Redis (24 h) |

## API Reference

### Health & Info

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/ok` | Liveness check |
| `GET` | `/health` | Health check (database + redis) |
| `GET` | `/info` | Server info and registered graphs |

### Assistants

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/assistants` | Create assistant |
| `GET` | `/assistants/{id}` | Get assistant |
| `PATCH` | `/assistants/{id}` | Update assistant |
| `DELETE` | `/assistants/{id}` | Delete assistant |
| `POST` | `/assistants/search` | Search assistants |
| `GET` | `/assistants/{id}/schemas` | Get input/output schemas |

### Agents (Agent Protocol)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/agents/search` | Search agents |
| `GET` | `/agents/{id}` | Get agent |
| `GET` | `/agents/{id}/schemas` | Get agent schemas |

### Threads

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/threads` | Create thread |
| `GET` | `/threads/{id}` | Get thread |
| `PATCH` | `/threads/{id}` | Update thread metadata |
| `DELETE` | `/threads/{id}` | Delete thread |
| `POST` | `/threads/search` | Search threads |
| `POST` | `/threads/{id}/copy` | Copy thread |
| `GET` | `/threads/{id}/state` | Get thread state |
| `POST` | `/threads/{id}/state` | Update thread state |
| `GET` | `/threads/{id}/history` | Get state history |

### Runs

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/runs/stream` | Stateless streaming run |
| `POST` | `/runs/wait` | Stateless blocking run |
| `POST` | `/runs` | Create background run |
| `POST` | `/runs/search` | Search runs |
| `GET` | `/runs/{id}` | Get run |
| `POST` | `/runs/{id}/cancel` | Cancel run |
| `DELETE` | `/runs/{id}` | Delete run |
| `GET` | `/runs/{id}/stream` | Join background run's SSE stream |
| `POST` | `/threads/{id}/runs/stream` | Stream run on thread |
| `POST` | `/threads/{id}/runs/wait` | Blocking run on thread |
| `POST` | `/threads/{id}/runs` | Background run on thread |
| `GET` | `/threads/{id}/runs` | List thread runs |
| `GET` | `/threads/{id}/runs/{rid}` | Get thread run |
| `GET` | `/threads/{id}/runs/{rid}/stream` | Join thread run stream |
| `POST` | `/threads/{id}/runs/{rid}/cancel` | Cancel thread run |

### Store

| Method | Path | Description |
|--------|------|-------------|
| `PUT` | `/store/items` | Put item |
| `GET` | `/store/items` | Get item by namespace + key |
| `DELETE` | `/store/items` | Delete item |
| `POST` | `/store/items/search` | Search items by namespace prefix |
| `POST` | `/store/namespaces` | List namespaces |

### Crons

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/runs/crons` | Create cron job |
| `PATCH` | `/runs/crons/{id}` | Update cron |
| `DELETE` | `/runs/crons/{id}` | Delete cron |
| `POST` | `/runs/crons/search` | Search crons |
| `POST` | `/threads/{id}/runs/crons` | Create thread-bound cron |

## SSE Wire Format

Compatible with `useStream()` React hook:

```
event: metadata
data: {"run_id": "..."}

event: values
data: {full_state_snapshot}

event: messages
data: [message_chunk, metadata]

event: end
data: null
```

Stream modes: `messages` (LLM chunks), `values` (full state after each node), `updates` (node deltas).

## Custom Authentication

Create an auth handler and reference it in `langgraph.json`:

```python
# auth.py
async def authenticate(headers: dict[str, str]) -> dict:
    token = headers.get("authorization", "").removeprefix("Bearer ")
    if not token:
        raise Exception("Missing token")
    # Validate token (JWT, DB lookup, etc.)
    return {"identity": "user-123", "role": "user"}
```

```json
{
  "auth": {
    "path": "./auth.py:authenticate"
  }
}
```

Unauthenticated paths: `/ok`, `/health`, `/info`, `/docs`, `/openapi.json`, `/redoc`.

## Background Runs

Background runs use **Dramatiq** with a Redis broker for at-least-once delivery:

1. API enqueues task via `handle_run.send_with_options()` → Redis RPUSH to `langrove` queue
2. Dramatiq `RedisBroker` atomically moves the message to a processing list (RPOPLPUSH / BLMOVE)
3. Worker `handle_run` actor executes the graph, publishes events via Redis Pub/Sub
4. Actor returns cleanly → Dramatiq deletes from processing list (ACKed)
5. On crash: message stays in processing list — Dramatiq's requeue thread re-delivers after timeout
6. After `max_delivery_attempts` failures: `DeadLetterMiddleware` writes to `langrove:tasks:dead` stream

**Queue name:** all background runs share a single Dramatiq queue named **`langrove`**.
Run cancellation is independent of the queue: the API sets a `langrove:runs:{run_id}:cancel` key in Redis; the actor polls for it after every streamed event and returns cleanly (no retry triggered) when found.

### Dead-letter queue

Failed messages that exhaust all retries land in a Redis stream at `langrove:tasks:dead`.

```bash
GET  /dead-letter          # list dead messages
POST /dead-letter/{id}/retry  # re-enqueue a specific message
```

## Multitask Strategies

When a thread already has an active run:

| Strategy | Behavior |
|----------|----------|
| `reject` | Return 409 Conflict (default) |
| `interrupt` | Cancel current run, start new |
| `rollback` | Revert to last checkpoint, start new |
| `enqueue` | Queue behind current run |

## Interrupt & Resume

Pause a graph at any node for human-in-the-loop:

```python
# Start a run that pauses before "review" node
async for event in client.runs.stream(
    thread_id, "agent",
    input={"messages": [{"role": "user", "content": "Draft a report"}]},
    interrupt_before=["review"],
):
    print(event)

# Resume with human feedback
async for event in client.runs.stream(
    thread_id, "agent",
    command={"resume": True},
    input={"messages": [{"role": "user", "content": "Approved, publish it"}]},
):
    print(event)
```

## CLI Reference

```
langrove serve   [--host HOST] [--port PORT] [--reload]
                 [--db-pool-min-size N] [--db-pool-max-size N]
                 [--log-level debug|info|warning|error]

langrove worker  [--worker-id ID]
                 [-Q QUEUE]              # queue to consume (repeatable; default: all)
                 [-t N / --concurrency N] # worker threads (default: 5)
                 [--max-retries N]        # delivery attempts before dead-letter (default: 3)
                 [--worker-timeout MS]    # idle-poll interval in ms (default: 5000)
                 [--task-timeout N]       # per-task timeout in seconds (default: 900)
                 [--shutdown-timeout N]   # graceful drain window in seconds (default: 30)
                 [--db-pool-min-size N] [--db-pool-max-size N]
                 [--log-level debug|info|warning|error]

langrove init    [--template chatbot]    # scaffold langgraph.json + agent.py
```

> `-Q` and `-t` use the same short forms as the upstream `dramatiq` CLI.

## Production Deployment

### Single-node Docker Compose

The included `docker-compose.yml` runs the full stack — API, worker, PostgreSQL, Redis:

```bash
# Build and start everything
docker compose up -d

# Run DB migrations (once, or on every deploy)
docker compose exec api uv run alembic upgrade head

# Scale to 3 workers
docker compose up -d --scale worker=3
```

Each worker connects to the same `langrove` Dramatiq queue on Redis and processes tasks independently. Dramatiq's RPOPLPUSH pattern ensures each message is claimed by exactly one worker.

### Production Environment Variables

Create a `.env` file (or inject via your secrets manager):

```dotenv
LANGROVE_DATABASE_URL=postgresql://user:pass@db-host:5432/langrove
LANGROVE_REDIS_URL=redis://:password@redis-host:6379

# Tune for your workload
LANGROVE_WORKER_CONCURRENCY=10          # threads per worker process
LANGROVE_TASK_TIMEOUT_SECONDS=600       # kill tasks running > 10 min
LANGROVE_MAX_DELIVERY_ATTEMPTS=3        # retries before dead-letter
LANGROVE_SHUTDOWN_TIMEOUT_SECONDS=60    # drain window on SIGTERM
LANGROVE_EVENT_STREAM_TTL_SECONDS=86400 # keep events for 24 h
```

### Separate API and Worker Images

The same Docker image runs both roles — the `CMD` (or `command:` in compose) selects the role:

```dockerfile
# API server
CMD ["uv", "run", "langrove", "serve", "--host", "0.0.0.0", "--port", "8123"]

# Worker
CMD ["uv", "run", "langrove", "worker", "--worker-id", "worker-1", "-Q", "langrove", "-t", "10"]
```

### Kubernetes

A minimal deployment with separate `Deployment` objects for the API and worker:

```yaml
# api-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: langrove-api
spec:
  replicas: 2
  template:
    spec:
      containers:
        - name: api
          image: your-registry/langrove:latest
          command: ["uv", "run", "langrove", "serve", "--host", "0.0.0.0", "--port", "8123"]
          ports:
            - containerPort: 8123
          envFrom:
            - secretRef:
                name: langrove-secrets
          readinessProbe:
            httpGet:
              path: /ok
              port: 8123
          livenessProbe:
            httpGet:
              path: /health
              port: 8123
---
# worker-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: langrove-worker
spec:
  replicas: 3                            # scale workers independently
  template:
    spec:
      containers:
        - name: worker
          image: your-registry/langrove:latest
          command:
            - uv
            - run
            - langrove
            - worker
            - --worker-id
            - $(POD_NAME)               # unique ID per pod
            - -Q
            - langrove
            - -t
            - "10"
            - --shutdown-timeout
            - "60"
          env:
            - name: POD_NAME
              valueFrom:
                fieldRef:
                  fieldPath: metadata.name
          envFrom:
            - secretRef:
                name: langrove-secrets
          lifecycle:
            preStop:
              exec:
                command: ["sleep", "5"]  # give time for SIGTERM to propagate
```

Key points:
- **Scale API and worker independently** — they are stateless; only PostgreSQL and Redis are stateful.
- **`--shutdown-timeout`** must be ≤ your pod `terminationGracePeriodSeconds` (default 30 s in Kubernetes). Set both to the same value, or set `terminationGracePeriodSeconds` slightly higher.
- **`$(POD_NAME)` as `--worker-id`** — makes logs easy to correlate with pod names.
- **`/ok`** for liveness, **`/health`** for readiness — the health endpoint checks DB + Redis connectivity.
- **DB migrations** should run as a Kubernetes `Job` (or init container) before the API deployment rolls out.

### Database Migrations in CI/CD

```bash
# Run once before rolling out a new version
docker run --rm \
  -e LANGROVE_DATABASE_URL=postgresql://... \
  your-registry/langrove:latest \
  uv run alembic upgrade head
```

### Scaling Workers

Worker count and thread count are independent:

| Scenario | Config |
|----------|--------|
| Low latency, many small tasks | More workers (`replicas`), fewer threads (`-t 2`) |
| Long-running LLM tasks | Fewer workers, more threads (`-t 10`) |
| Mixed workload | Separate worker deployments per queue (future) |

Each worker thread can handle one Dramatiq message at a time. With `AsyncIO` middleware, async actors within a worker share one event loop, so `-t 10` → up to 10 concurrent graph executions per worker process.

### Health Checks

| Endpoint | Use |
|----------|-----|
| `GET /ok` | Liveness — returns `200` immediately if the process is alive |
| `GET /health` | Readiness — checks PostgreSQL + Redis connectivity; returns `503` if either is down |

### Redis Key Namespace

All Langrove keys share the `langrove:` prefix:

| Key pattern | Type | Purpose |
|---|---|---|
| `langrove` | List | Dramatiq task queue (RPUSH / BLMOVE) |
| `langrove.processing` | List | Dramatiq in-flight messages (RPOPLPUSH) |
| `langrove:tasks:dead` | Stream | Dead-lettered messages (exhausted retries) |
| `langrove:runs:{id}:stream` | Pub/Sub channel | Live event relay for background runs |
| `langrove:runs:{id}:events` | Stream | Stored events for replay / reconnection |
| `langrove:runs:{id}:cancel` | Key | Cancellation signal polled by the actor |

## Docker Deployment

```bash
# Full stack (API + worker + postgres + redis)
docker compose up -d

# Infrastructure only (for local development with uv)
docker compose up postgres redis -d

# Scale workers
docker compose up -d --scale worker=3
```

## Examples

| Example | What it demonstrates |
|---------|---------------------|
| [`examples/quickstart/`](examples/quickstart/) | Basic setup, streaming, threads, SDK client |
| [`examples/custom-auth/`](examples/custom-auth/) | JWT/API key auth handler, authenticated client |
| [`examples/multi-agent-store/`](examples/multi-agent-store/) | Multiple graphs, store API, crons, interrupt/resume, multitask strategies |

## Project Structure

```
src/langrove/
  cli.py              # Click CLI (serve, worker, init)
  settings.py          # Pydantic BaseSettings (LANGROVE_ prefix)
  config.py            # langgraph.json parser
  app.py               # FastAPI app factory
  worker.py            # Background worker main loop
  exceptions.py        # Domain exceptions
  models/              # Pydantic DTOs
  db/                  # asyncpg repositories (raw SQL)
  services/            # Business logic (one service per domain)
  graph/               # Graph loading + registry
  streaming/           # SSE executor, formatter, broker
  queue/               # Dramatiq broker (broker.py), actor (tasks.py), publisher (publisher.py)
  auth/                # Auth handlers + middleware
  api/                 # FastAPI route handlers (thin, delegate to services)

.claude/
  settings.json        # Claude Code hooks + agent teams config
  agents/              # Subagent definitions (architect, implementer, reviewer)
  journals/            # Agent learnings across sessions

.github/
  workflows/           # CI + autonomous agent workflows
  ISSUE_TEMPLATE/      # Structured templates for features and bugs
```

## Development

```bash
# Install dependencies
uv sync

# Run linter
uv run ruff check .

# Run formatter
uv run ruff format .

# Run tests
uv run pytest

# Run migrations
uv run alembic upgrade head
```

## Autonomous Development (AI-Assisted)

Langrove uses a fully automated development lifecycle powered by Claude Code, inspired by the [Helios Black Hole Architecture](https://deepwiki.com/BintzGavin/helios/1.3-ai-assisted-development-model).

### How it works

```
Planning (weekly)  →  Creates GitHub Issues from README vision + codebase gaps
       ↓
Execution (on label / every 6h)  →  Implements issue → branch → test → PR
       ↓
Review (on PR)  →  Automated code review + CI (lint + tests)
       ↓
Merge (on CI pass)  →  Auto-merge Claude's PRs
       ↓
Maintenance (weekly)  →  Deps, docs, dead code cleanup
```

### GitHub Actions Workflows

| Workflow | Trigger | What it does |
|----------|---------|--------------|
| `ci.yml` | Push / PR | Lint (ruff) + test (pytest) |
| `claude.yml` | `@claude` mention | Interactive AI agent in issues/PRs |
| `claude-review.yml` | PR opened | Automated code review |
| `claude-implement.yml` | Issue labeled `claude` | Autonomous implementation → PR |
| `claude-backlog.yml` | Every 6 hours | Picks up and implements backlog items |
| `claude-planner.yml` | Weekly (Monday) | Analyzes codebase, creates issues |
| `claude-maintenance.yml` | Weekly (Sunday) | Dependency and documentation updates |
| `auto-merge.yml` | PR from `claude/*` branch | Auto-merge after CI passes |

### Local Agent Teams

For complex features, spawn a team of specialized Claude Code agents:

```
Create an agent team to implement issue #42:
- Spawn an architect teammate to plan the approach
- Spawn 2 implementer teammates to build different modules
- Spawn a reviewer teammate to review their work
Require plan approval before implementation begins.
```

Subagent definitions in `.claude/agents/` (architect, implementer, reviewer).

### Agent Journals

Agents store learnings in `.claude/journals/` (checked into git) so knowledge persists across CI runs. Each agent reads its journal before starting and appends new insights after completing work.

## Principles

- KISS, YAGNI, SOLID
- Raw asyncpg SQL, no ORM
- Services receive dependencies via constructor injection
- API handlers are thin — delegate to services
- No speculative abstractions — add when a second implementation appears

## License

MIT
