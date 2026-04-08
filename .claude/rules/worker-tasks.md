---
description: Redis Streams task queue, consumer groups, late-ack delivery, recovery, and worker lifecycle
globs:
  - "src/langrove/queue/**/*.py"
  - "src/langrove/worker.py"
---

# Worker & Task Queue

## Redis Streams Architecture
- Task stream: `langrove:tasks`
- Consumer group: `langrove:workers`
- Worker ID: `worker-{uuid.hex[:8]}` (auto-generated)
- Payload: single field `{"payload": orjson.dumps(full_dict).decode()}`

## Late Acknowledgment (At-Least-Once Delivery)
1. `XREADGROUP` reads from stream → enters Pending Entries List (PEL)
2. Worker processes task
3. `XACK` only on success → removes from PEL
4. On failure: DON'T ACK → task remains in PEL for recovery

## Consumer Behavior
- First checks pending messages: `XREADGROUP {..., "0"}` (reads from PEL)
- Then reads new messages: `XREADGROUP {..., ">"}` (new only)
- Blocking: `block=5000` (5 seconds) if no new messages
- Deduplication: `_in_flight_ids` set prevents multiple slots claiming same pending message

## Concurrency
- `asyncio.Semaphore(concurrency)` limits concurrent tasks (default 5)
- Task tracking: `asyncio.create_task()` + `add_done_callback(tasks.discard)` for auto-cleanup
- In-flight tasks stored in `self._tasks` set for graceful shutdown

## Recovery Monitor (queue/recovery.py)
- Runs every 30 seconds (configurable `interval_seconds`)
- `XAUTOCLAIM` reclaims tasks idle > `timeout_ms` (default 900s = 15 min)
- Poison message detection: `XPENDING` checks `times_delivered` count
- If delivery count > `max_attempts` (default 3):
  1. XADD to dead-letter stream: `langrove:tasks:dead`
  2. XACK original message
  3. XDEL from main stream
  4. Callback: `on_reclaim(run_id)` updates DB run status

## Cancel Mechanism
- API sets Redis key: `SET langrove:runs:{run_id}:cancel` (TTL 3600s)
- Worker polls: `EXISTS cancel_key` after each streaming event
- On cancel: break generator loop, return gracefully

## Graceful Shutdown (Two-Phase)
1. **First SIGTERM:** set `shutdown_event`, cancel main loop (consumer + recovery)
2. **Second SIGTERM:** set `force_quit`, cancel all in-flight tasks immediately
3. Wait for in-flight with timeout: `asyncio.wait(tasks, timeout=30)`
4. Cleanup: close psycopg pools (checkpointer, store), asyncpg pool, Redis client

## Worker Task Handler Flow
```
1. Publish metadata event (run_id)
2. Update run status → "running"
3. Set thread status → "busy"
4. async for part in executor.execute_stream():
     - Check cancel_key (break if exists)
     - Publish event to Redis pub/sub
     - Store event in Redis Stream
5. Publish end event
6. Update run status → "success"
7. Set thread status → "idle"
```

## Gotchas
- Unacked tasks stay in PEL across restarts — recovery reclaims them
- Thread status may get stuck "busy" if worker crashes mid-run (recovery only updates run status)
- Dead-lettered messages are never auto-retried — manual inspection via `/dead-letter` endpoint
- XAUTOCLAIM requires consumer group to exist; gracefully suppresses errors if not ready
- Event publishing during execution: pub/sub (live) + Streams (replay) — both written per event

## 2026-04-08: Taskiq replaces custom Redis Streams consumer
- **Library:** `taskiq` + `taskiq-redis` (RedisStreamBroker) replaced hand-rolled `TaskConsumer` + `RecoveryMonitor`
- **Why Taskiq over alternatives:** asyncio-native; `RedisStreamBroker` uses XREADGROUP/XACK natively (true late-ack); 2.1k stars, active. ARQ is in maintenance mode. Dramatiq requires a thread-based asyncio shim. SAQ only 836 stars.
- **Late-ack:** Taskiq's `RedisStreamBroker` uses Redis Streams consumer groups — message not XACK'd until task function returns without raising. Crash = message stays in PEL and is reclaimed automatically by Taskiq.
- **Retry / dead-letter:** `SimpleRetryMiddleware(default_retry_count=N)` + `broker.register_task(..., retry_on_error=True, max_retries=N)`. On last attempt failure, `handle_run` manually XADDs to `langrove:tasks:dead` stream (preserves `/dead-letter` API compatibility).
- **DI pattern:** `ctx: Context = TaskiqDepends()` injects broker state into task functions. `state.*` fields set up in `WORKER_STARTUP` hook.
- **Worker startup/shutdown:** `@broker.on_event(TaskiqEvents.WORKER_STARTUP/SHUTDOWN)` hooks replace the inline resource init/cleanup in the old `run_worker()`.
- **Programmatic runner:** `Receiver(broker, max_async_tasks=N)` → `receiver.listen()` replaces the custom consumer loop. No CLI needed.
- **Publisher:** API server creates a publisher-only broker (`RedisStreamBroker`, `broker.startup()` only, no `Receiver`). Uses `broker.kick(TaskiqMessage(...))` to enqueue.
- **Dead-letter retry endpoint:** Uses `task_broker.kick(TaskiqMessage(...))` instead of raw `redis.xadd(TASK_STREAM, fields)` so retried jobs go through the normal Taskiq pipeline.
