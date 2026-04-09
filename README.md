# Langrove

Open-source, self-hosted drop-in replacement for LangGraph deployment (LangSmith Deployments).

Works with `langgraph_sdk.get_client()`, the `useStream()` React hook, and [Agent Chat UI](https://github.com/langchain-ai/agent-chat-ui). Agent Protocol compliant.

## Why Langrove?

LangGraph Cloud is proprietary and requires LangSmith. Langrove gives you the same API surface — assistants, threads, runs, streaming, store, crons — on your own infrastructure. Deploy anywhere: bare metal, Docker, Kubernetes.

## Features

- **Full LangGraph SDK compatibility** — `get_client()` works out of the box
- **SSE streaming** — `useStream()` compatible wire format (messages, values, updates)
- **Background runs** — Redis Streams with at-least-once delivery, crash recovery, dead-letter queue
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
uv run langrove migrate

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
                    │  (Streams +  │
                    │   Pub/Sub)   │
                    └──────┬───────┘
                           │
                           ▼
                    ┌──────────────┐
                    │   Worker     │
                    │  (graph      │
                    │  execution)  │
                    └──────────────┘
```

- **API Server** (FastAPI/uvicorn) — HTTP endpoints, SSE streaming for foreground runs
- **Worker** — Consumes background tasks from Redis Streams, executes LangGraph graphs
- **PostgreSQL** — Threads, runs, assistants, store, crons + LangGraph checkpoint tables
- **Redis** — Task queue (Streams + consumer groups), live stream relay (Pub/Sub), event replay

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

All variables use the `LANGROVE_` prefix and are optional — every one has a sensible default.

**Infrastructure**

| Variable | Default | Description |
|----------|---------|-------------|
| `LANGROVE_DATABASE_URL` | `postgresql://langrove:langrove@localhost:5432/langrove` | asyncpg connection string |
| `LANGROVE_REDIS_URL` | `redis://localhost:6379` | Redis URL for queue and pub/sub |

**Server**

| Variable | Default | Description |
|----------|---------|-------------|
| `LANGROVE_HOST` | `0.0.0.0` | Bind address |
| `LANGROVE_PORT` | `8123` | Bind port |
| `LANGROVE_CONFIG_PATH` | `langgraph.json` | Path to `langgraph.json` |

**Connection pools**

| Variable | Default | Description |
|----------|---------|-------------|
| `LANGROVE_DB_POOL_MIN_SIZE` | `2` | Min asyncpg connections (app queries) |
| `LANGROVE_DB_POOL_MAX_SIZE` | `10` | Max asyncpg connections (app queries) |
| `LANGROVE_CHECKPOINTER_POOL_MAX_SIZE` | `5` | Max psycopg connections (checkpointer) |
| `LANGROVE_STORE_POOL_MAX_SIZE` | `5` | Max psycopg connections (store) |

**Worker**

| Variable | Default | CLI flag | Description |
|----------|---------|----------|-------------|
| `LANGROVE_WORKER_CONCURRENCY` | `5` | `-t/--concurrency` | Concurrent async tasks per worker |
| `LANGROVE_TASK_TIMEOUT_SECONDS` | `900` | `--task-timeout` | Max task execution time (seconds) |
| `LANGROVE_MAX_DELIVERY_ATTEMPTS` | `3` | `--max-retries` | Retries before dead-letter |
| `LANGROVE_SHUTDOWN_TIMEOUT_SECONDS` | `30` | `--shutdown-timeout` | Graceful shutdown wait (seconds) |
| `LANGROVE_QUEUE_NAME` | `langrove` | `-Q/--queues` | Redis queue name |

**Events**

| Variable | Default | Description |
|----------|---------|-------------|
| `LANGROVE_EVENT_STREAM_TTL_SECONDS` | `86400` | SSE event retention in Redis (24 hours) |

**Loading order** (last wins): system env → `langgraph.json` `env` field → CLI flags.

The `env` field in `langgraph.json` accepts either a path to a `.env` file (resolved relative to the config file) or an inline dict:

```jsonc
{
  "env": ".env"
  // or: "env": { "LANGROVE_DATABASE_URL": "postgresql://..." }
}
```

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

Background runs use Redis Streams with late acknowledgment for crash resilience:

1. API publishes task to Redis Stream (`XADD`)
2. Worker reads via consumer group (`XREADGROUP`) — enters Pending Entries List
3. Worker executes graph, publishes events via Pub/Sub
4. Worker acknowledges only after success (`XACK`)
5. On crash: `XAUTOCLAIM` reclaims unacked tasks after timeout
6. Poison messages (>3 attempts): moved to dead-letter stream

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

## Docker Deployment

```bash
# Full stack
docker compose up

# Or just infrastructure (for local development)
docker compose up postgres redis -d
```

The `docker-compose.yml` includes API server, worker, PostgreSQL (pgvector), and Redis.

## CLI Reference

```bash
langrove serve [--host 0.0.0.0] [--port 8123] [--reload]
langrove worker [--worker-id ID] [-t CONCURRENCY] [--task-timeout SECS] [--max-retries N] [--shutdown-timeout SECS] [-Q QUEUE]
langrove init [--template chatbot]
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
  settings.py          # Pydantic BaseSettings
  config.py            # langgraph.json parser
  app.py               # FastAPI app factory
  worker.py            # Background worker main loop
  exceptions.py        # Domain exceptions
  models/              # Pydantic DTOs
  db/                  # asyncpg repositories (raw SQL)
  services/            # Business logic (one service per domain)
  graph/               # Graph loading + registry
  streaming/           # SSE executor, formatter, broker
  queue/               # Redis Streams publisher, consumer, recovery
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
uv run langrove migrate
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
