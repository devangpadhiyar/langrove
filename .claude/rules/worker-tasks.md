---
description: Dramatiq task queue, at-least-once delivery, cancellation, dead-letter, and worker lifecycle
globs:
  - "src/langrove/queue/**/*.py"
  - "src/langrove/worker.py"
---

# Worker & Task Queue

## Library: Dramatiq + RedisBroker
- **Package:** `dramatiq[redis]` (v2.1.0+, 5.2k stars, actively maintained)
- **Why Dramatiq over alternatives:**
  - ARQ: maintenance mode
  - Taskiq: asyncio-native but smaller community (2.1k stars); RedisStreamBroker late-ack is native but library surface is larger
  - SAQ: only 836 stars
  - Dramatiq: largest community, built-in retries/dead-letter, `AsyncIO` middleware enables async actors

## Late Acknowledgment (At-Least-Once Delivery)
Dramatiq's `RedisBroker` uses an atomic RPOPLPUSH / BLMOVE pattern:
1. Worker atomically moves message from `langrove:queue` → `langrove:queue.processing` list
2. Actor runs
3. On success: message deleted from processing list (ACKed)
4. On crash / failure: message stays in processing list — Dramatiq's requeue thread reclaims it after timeout and re-delivers
5. No custom consumer groups or XAUTOCLAIM needed

## Middleware Stack (registered in `queue/broker.py`)
```
RedisBroker
  ├── AsyncIO()          — one shared event loop per worker process; async actors run concurrently
  ├── TimeLimit()        — kills actors exceeding task_timeout_ms (default 900 000 ms)
  ├── Retries()          — exponential backoff, up to max_delivery_attempts (default 3)
  └── DeadLetterMiddleware() — after final retry failure: XADD to langrove:tasks:dead stream
```
Middleware order matters: `Retries` runs before `DeadLetterMiddleware` so dead-lettering only happens after all retries are exhausted.

## Broker Setup (import order is critical)
`setup_broker()` in `queue/broker.py` **must** be called before `queue/tasks.py` is imported.
The `@dramatiq.actor` decorator registers the actor with whichever broker is current at import time.
- **API server:** called in `app.py` lifespan before any request handler imports tasks
- **Worker process:** called in `worker.py` before `from langrove.queue.tasks import handle_run`
- **Publisher / dead-letter retry:** use lazy imports so `setup_broker()` is guaranteed to have run first

## Worker Resources (Lazy Initialisation)
All worker-scoped resources (DB pool, Redis client, checkpointer, store, executor, event broker)
are initialised lazily on the **first task invocation** in `queue/tasks.py`:

```python
_state: dict | None = None
_state_lock: asyncio.Lock | None = None

async def _get_state() -> dict:
    global _state, _state_lock
    if _state_lock is None:
        _state_lock = asyncio.Lock()
    async with _state_lock:
        if _state is None:
            _state = await _setup_resources()
    return _state
```

`asyncio.Lock` is safe here because Dramatiq's `AsyncIO` middleware runs all async actors on a single shared event loop per worker process.

## Actor Definition
```python
@dramatiq.actor(queue_name="langrove", max_retries=3)
async def handle_run(**payload) -> None:
    state = await _get_state()
    ...
```
- `queue_name="langrove"` — all background runs share one queue
- `max_retries=3` — overrides the `Retries` middleware default; `DeadLetterMiddleware` fires after the 3rd failure

## Publisher (API → Worker)
```python
# queue/publisher.py
await asyncio.to_thread(handle_run.send_with_options, kwargs=payload)
```
- `send_with_options` is synchronous (Redis RPUSH); `asyncio.to_thread` keeps the API event loop non-blocking
- No broker reference needed — uses the global broker set by `setup_broker()`
- `TaskPublisher()` takes no constructor arguments

## Cancellation Mechanism
Cancellation is independent of Dramatiq — it is a custom Redis key polling pattern inside the actor:
1. API calls `cancel_run()` → sets `langrove:runs:{run_id}:cancel` key in Redis
2. `handle_run` actor polls `redis.exists(cancel_key)` after **every** streamed event
3. On detection: breaks the stream loop, publishes `RunCancelled` SSE terminal event, deletes key, `return`s cleanly
4. Clean `return` → Dramatiq ACKs the message (no retry triggered)

This works with any task queue library — Dramatiq has no involvement in the cancellation path.

## Dead-Letter Stream
- Stream key: `langrove:tasks:dead` (Redis Stream, same format as before)
- Written by `DeadLetterMiddleware.after_process_message` when `current_retries >= actor.max_retries`
- Uses synchronous `redis` client (Dramatiq runs in threads, not the async event loop)
- `/dead-letter` GET endpoint reads via `aioredis.xrange`
- `/dead-letter/{id}/retry` re-enqueues via `asyncio.to_thread(handle_run.send_with_options, kwargs=payload)`

## Graceful Shutdown (Two-Phase)
1. **First SIGTERM:** sets `shutdown_event`; worker drains in-flight via `worker.stop(join=True)` in executor (timeout = `settings.shutdown_timeout_seconds`, default 30s)
2. **Drain timeout exceeded:** `asyncio.wait_for` raises `TimeoutError`; falls back to `worker.stop(join=False)` immediately
3. **Second SIGTERM (before drain completes):** sets `force_quit`; calls `worker.stop(join=False)` immediately
4. Cleanup: worker threads exit; lazy `_state` resources (DB, Redis pools) are not explicitly closed on shutdown (process exit handles them)

## Worker Concurrency
- `dramatiq.Worker(broker, worker_threads=settings.worker_concurrency)` — default 5 threads
- Each thread runs one Dramatiq message at a time
- With `AsyncIO` middleware, all async actors share one event loop: effective async concurrency = `worker_threads`

## CLI Options (`langrove worker`)
- `--worker-id ID` — logged at startup for process identification (default: "worker-default")
- `--concurrency N` — overrides `LANGROVE_WORKER_CONCURRENCY` (default: 5)
- `--task-timeout N` — task timeout in seconds, overrides `LANGROVE_TASK_TIMEOUT_SECONDS` (default: 900)
- `--shutdown-timeout N` — graceful drain timeout in seconds, overrides `LANGROVE_SHUTDOWN_TIMEOUT_SECONDS` (default: 30)
- `--db-pool-min-size` / `--db-pool-max-size` — asyncpg pool bounds for worker DB connections

## Gotchas
- `setup_broker()` must precede any `from langrove.queue.tasks import handle_run` — import order is critical
- Dramatiq's `AsyncIO` middleware creates the event loop lazily on first async actor; `_state_lock` must be initialised inside the loop (not at module level)
- Dead-letter middleware uses synchronous `redis` (not `aioredis`) because `after_process_message` runs on a Dramatiq worker thread, not the async event loop
- `TaskPublisher()` constructor takes no arguments; the global Dramatiq broker is used implicitly
- Thread status may remain "busy" if the worker process is hard-killed (no graceful shutdown) — no automatic recovery beyond the DB run status update on next delivery attempt
- Event publishing during execution: pub/sub (live) + Redis Streams (replay) — both written per event; unchanged from before

## 2026-04-08: Dramatiq replaces custom Redis Streams consumer
- Deleted: `queue/consumer.py` (XREADGROUP loop), `queue/recovery.py` (XAUTOCLAIM monitor)
- Added: `queue/broker.py` (setup_broker + DeadLetterMiddleware), updated `queue/tasks.py`, `queue/publisher.py`, `worker.py`
- Late-ack preserved via Dramatiq `RedisBroker` RPOPLPUSH processing-list pattern
- Cancellation unchanged: Redis key polling inside `handle_run` actor
- Dead-letter stream (`langrove:tasks:dead`) and `/dead-letter` API fully compatible
