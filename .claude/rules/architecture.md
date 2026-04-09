---
description: System architecture, graph loading, app lifecycle, and cross-cutting patterns
globs:
  - "src/langrove/**/*.py"
---

# Architecture

## Graph Instance Per Request
- Base graphs loaded at startup into `GraphRegistry` — cached without checkpointer (immutable, shared)
- Per-request: `graph.copy(update={...})` injects checkpointer + store
- Config deep-copied per request via `deepcopy(config)` to prevent concurrent mutations
- Fallback to shallow copy if deepcopy fails (e.g., non-serializable objects like LangfuseResourceManager)

## Graph Loading (graph/loader.py)
- Dynamic module loading: `importlib.util.spec_from_file_location()` from `"./path/to/module.py:attribute"` specs
- Parent directory auto-added to `sys.path` for transitive imports
- Relative paths resolve against config file directory, NOT cwd

## App Factory (app.py)
- `create_app()` with `@asynccontextmanager` for async lifespan
- **Startup order:** (CLI loads .env first) → asyncpg pool → Redis → load graphs → setup checkpointer (psycopg) → setup store (psycopg) → auto-create assistants
- **Shutdown:** close all pools (checkpointer, store, db, redis)
- State on `app.state`: `db_pool`, `redis`, `graph_registry`, `checkpointer`, `store`, `settings`, `config`

## Middleware Stack
1. CORS (configured from `config.http.cors`)
2. Auth (if `config.auth.path` set) — see `.claude/rules/auth.md`

## Two Database Pool Types
- **asyncpg** (`db/pool.py`): app-level queries (threads, runs, assistants, store, crons)
- **psycopg** (`db/langgraph_pools.py`): LangGraph checkpointer + store (separate pools, autocommit=True)

## Streaming Architecture
- **Foreground:** `asyncio.Queue` per run_id — publish/subscribe within same process
- **Background:** Redis pub/sub (live events) + Redis Streams (replay/reconnection)
- See `.claude/rules/streaming.md` for details

## Thread State Lifecycle
- Status: `idle` → `busy` → `success|error` → `idle`
- Thread `values` and `interrupts` are NOT stored in threads table — derived from LangGraph checkpointer at read time

## Ephemeral Threads
- Created when no `thread_id` provided and `on_completion="delete"`
- Auto-deleted in generator `finally` block after stream completes

## Config File (langgraph.json)
- Parsed by `config.py` with Pydantic models
- Fallback loading: `langgraph.json` → `aegra.json` → defaults
- `.env` path in config resolves relative to config file directory
- Graphs: `{"graph_id": "./path/to/module.py:attribute"}`

## CLI Commands (cli.py)
- `langrove serve` — FastAPI via uvicorn (default port 8123)
- `langrove worker` — Redis Streams consumer + recovery monitor
- `langrove init` — scaffold langgraph.json + agent.py
- Both `serve` and `worker` accept `--config` to point at a non-default `langgraph.json`
- `.env` loading happens in `_load_dotenv_from_config()` at CLI layer, before any langrove module import — this ensures module-level `Settings()` singletons (e.g. Celery app) see the correct env vars
- 2026-04-09: `.env` must be loaded at CLI level (not app factory) so Celery's module-level Settings() singleton picks it up; loading in app.py is too late

## Settings (settings.py)
- Pydantic BaseSettings with `env_prefix="LANGROVE_"` and `.env` file support
- Key defaults: DB pool 2-10, checkpointer pool 5, store pool 5, worker concurrency 5, task timeout 900s, event TTL 86400s (24h)

## Gotchas
- Multiple workers each spawn all pools — can exhaust PostgreSQL max_connections quickly
- Auth user injected into graph configurable as `langgraph_auth_user` key
- `asyncio.aclosing()` required for astream() generator cleanup (releases checkpoint locks)
