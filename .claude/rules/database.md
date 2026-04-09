---
description: asyncpg query patterns, JSONB handling, connection pools, and migration conventions
globs:
  - "src/langrove/db/**/*.py"
  - "migrations/**/*.py"
---

# Database

## asyncpg JSONB Handling
- asyncpg returns JSONB as JSON-encoded strings. The custom codec in `db/pool.py` uses `orjson.loads()` which may need two passes (first unwraps outer quotes, second extracts the object)
- Encoder: `orjson.dumps(v).decode()` — must decode bytes to string for PostgreSQL
- Codec registration uses "text" format (not "binary") via `init` callback on pool creation

## Query Patterns
- ALL queries use `$N` positional parameters — never f-strings or string interpolation (SQL injection prevention)
- JSONB inserts require explicit `::jsonb` cast: `VALUES ($1::jsonb)`
- Dynamic WHERE building: track `idx` counter, append conditions + args in lockstep
  ```python
  conditions.append(f"{key} = ${idx}")
  args.append(value)
  idx += 1
  ```
- JSONB containment operator: `metadata_ @> $N::jsonb` with `orjson.dumps(dict).decode()`
- Only interpolate known field names into SQL — parameters always use $N placeholders

## Field Naming
- DB column `metadata_` (reserved word escape) → normalized to `metadata` in Python dicts
- All repositories call `_normalize()` to handle this rename
- Config/JSON columns use `::jsonb` cast on INSERT/UPDATE

## Store Namespace
- PostgreSQL `ARRAY(TEXT)` type for hierarchical keys
- Queried via array slice: `namespace[1:{len(prefix)}]` — positional, not semantic
- Composite PK: `(namespace, key)`

## Connection Pools
- asyncpg: min=2, max=10 (app-level queries via `db/pool.py`)
- psycopg: max=5 each (LangGraph checkpointer + store via `db/langgraph_pools.py`)
- Total up to 20 connections per server instance — watch for PostgreSQL `max_connections` exhaustion with multiple workers
- psycopg pools use `autocommit=True, prepare_threshold=0`

## Transactions & Atomicity
- No explicit transactions in repositories — each method is a single atomic query
- Multi-step operations (create run + update status) are NOT transactional

## Version Snapshots
- `ON CONFLICT (assistant_id, version) DO NOTHING` for idempotent history writes
- Version auto-incremented on UPDATE before INSERT into versions table

## Gotchas
- `orjson.dumps(None)` produces `"null"` string — correct for PostgreSQL NULL JSONB
- Store items have no indices beyond PK — could bottleneck on large stores
- Pool acquisition: `async with self.pool.acquire() as conn` — single connection per query
- All `fetch_*` methods return dicts via `dict(row)` conversion from asyncpg.Record
- 2026-04-07: Checkpointer pool is psycopg (not asyncpg) — uses `%s` placeholders, acquired via `async with checkpointer.conn.connection() as conn`. The `$N` asyncpg convention applies only to the app-level `DatabasePool`, not the checkpointer/store psycopg pools.
- 2026-04-09: When writing Alembic downgrade paths that recreate indexes, list the exact column names explicitly rather than inferring from index name via `split("_")[-1]` — the inference is fragile (e.g. `idx_runs_thread_id.split("_")[-1]` → `"id"` not `"thread_id"`).
- 2026-04-09: Startup schema check uses SQLAlchemy (not asyncpg) for Alembic compatibility — wrap in `asyncio.to_thread` to avoid blocking the async lifespan. Skip silently if `alembic.ini` not found (wheel installs without migration tooling).
