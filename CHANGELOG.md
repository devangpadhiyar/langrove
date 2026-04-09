# Changelog

All notable changes to Langrove are documented here.

## [0.2.1] - 2026-04-09

### Changed

- README: corrected and expanded environment variables reference — all `LANGROVE_*` prefixed variables now documented with defaults, descriptions, and loading order explanation.
- Added `CHANGELOG.md` with release history back to 0.1.0.

---

## [0.2.0] - 2026-04-09

### Breaking Changes

- **Worker replaced**: Dramatiq + Redis Streams consumer has been replaced with **Celery + celery-aio-pool**. The worker is now started with `langrove worker` (same CLI) but uses `AsyncIOPool` under the hood. Update any process supervisors or Docker Compose configs to set `CELERY_CUSTOM_WORKER_POOL=celery_aio_pool.pool:AsyncIOPool` (set automatically by the CLI).

### Added

- **Celery worker** (`queue/celery_app.py`, `queue/tasks.py`, `queue/publisher.py`) — async task execution via `celery-aio-pool`, with `task_acks_late=True` and `task_reject_on_worker_lost=True` for at-least-once delivery on worker crash.
- **Dead-letter queue** — tasks exceeding `max_delivery_attempts` (default 3) are written to a Redis Stream (`langrove:tasks:dead`) and exposed via `/dead-letter` API endpoints.
- **Run cancellation** — `POST /runs/{id}/cancel` sets a Redis cancel key and revokes the Celery task; worker polls and exits cleanly mid-stream.
- **Cross-thread store** — hierarchical key-value store backed by `AsyncPostgresStore` (LangGraph), with namespace search and prefix listing.
- **`on_disconnect=continue` support** — background runs continue executing even if the client disconnects from the SSE stream; reconnect via `GET /runs/{id}/stream`.
- **Thread copy** — `POST /threads/{id}/copy` now duplicates full checkpoint history, not just thread metadata.
- **Environment variable reference** — full `LANGROVE_*` variable documentation added to README.

### Fixed

- `.env` now loaded at the CLI layer before the Celery `Settings()` singleton is instantiated, so env vars are correctly visible to the worker process.
- Removed unused `_CONFIG_FILENAMES` constant (YAGNI cleanup).

### Dependencies

- Added: `celery[redis]>=5.3.0`, `celery-aio-pool>=0.1.0rc8`
- Removed: `dramatiq[redis]`, Redis Streams consumer loop

---

## [0.1.0] - 2026-03-01

Initial release.

- FastAPI server with full LangGraph SDK-compatible API surface (assistants, threads, runs, store, crons)
- SSE streaming compatible with `useStream()` React hook and Agent Chat UI
- PostgreSQL-backed threads, runs, assistants, checkpoints (asyncpg + psycopg)
- Redis pub/sub for live stream relay and event replay on reconnect
- Dramatiq + Redis Streams background worker (replaced in 0.2.0)
- Custom auth handler support (`langgraph.json` `auth.path`)
- Interrupt/resume, multitask strategies (reject, interrupt, rollback, enqueue)
- Agent Protocol `/agents` endpoints
- Alembic migrations
- `langrove init` scaffold command
- Docker Compose for full-stack local development
