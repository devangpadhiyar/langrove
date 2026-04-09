---
description: Celery task queue with celery-aio-pool, late-ack delivery, dead-letter handling, and worker lifecycle
globs:
  - "src/langrove/queue/**/*.py"
  - "src/langrove/worker.py"
---

# Worker & Task Queue

## Celery Architecture (celery-aio-pool)
- Celery app defined in `queue/celery_app.py` -- module-level singleton
- Task queue: Redis list named by `settings.queue_name` (default: `langrove`)
- celery-aio-pool provides `AsyncIOPool` -- async tasks run on a shared event loop per worker process
- Env var `CELERY_CUSTOM_WORKER_POOL=celery_aio_pool.pool:AsyncIOPool` must be set before worker starts
- Worker started via `app.worker_main(argv)` -- synchronous call, Celery manages its own event loop

## Late Acknowledgment (At-Least-Once Delivery)
- `task_acks_late=True` -- Celery ACKs only after task function returns/raises
- `task_reject_on_worker_lost=True` -- re-queues task if worker process crashes
- `worker_prefetch_multiplier=1` -- fetches one task at a time (required with acks_late)
- `visibility_timeout = task_timeout_seconds * 2` -- prevents mid-execution re-delivery

## Retry & Dead-Letter
- `max_retries=3` on the `handle_run` task (configurable via `max_delivery_attempts` setting)
- `self.retry(exc=exc, countdown=30)` in the except handler
- On `MaxRetriesExceededError`: write payload to `langrove:tasks:dead` Redis stream, then re-raise
- Dead-lettered messages inspected via `/dead-letter` API, retried via `/dead-letter/{id}/retry`

## Cancel Mechanism
- API sets Redis key: `SET langrove:runs:{run_id}:cancel` (TTL 3600s)
- API also calls `app.control.revoke(run_id, terminate=False)` for queued-but-not-started tasks
- Worker polls: `EXISTS cancel_key` after each streaming event
- On cancel: break generator loop, return cleanly (no retry triggered)

## Worker Resources (Lazy Init)
- Resources (DB pool, Redis, checkpointer, store, executor) initialised on first task via `_get_state()`
- Protected by `asyncio.Lock` -- safe because celery-aio-pool uses a single event loop per process
- Cleanup via `worker_process_shutdown` Celery signal

## Worker Task Handler Flow
```
1. Delete stale cancel key
2. Update run status -> "running"
3. Set thread status -> "busy"
4. Publish metadata event (run_id)
5. async for part in executor.execute_stream():
     - Check cancel_key (break if exists)
     - Publish event to Redis pub/sub
     - Store event in Redis Stream
6. Publish end event
7. Update run status -> "success"
8. Set thread status -> "idle"
```

## TaskPublisher (API side)
- `TaskPublisher()` takes no constructor args -- Celery app is module-level
- `publish()` calls `handle_run.apply_async(kwargs=payload, task_id=run_id, queue=queue_name)`
- `apply_async` is synchronous (Redis LPUSH) -- wrapped in `asyncio.to_thread`
- `task_id=run_id` enables revoke-by-run-id for cancellation

## CLI Worker Command
- `langrove worker` calls `run_worker()` directly (synchronous, no `asyncio.run()`)
- Flags: `--worker-id`, `-Q/--queues`, `-t/--concurrency`, `--max-retries`, `--task-timeout`, `--shutdown-timeout`

## Gotchas
- `run_worker()` is synchronous -- Celery's `app.worker_main()` blocks and manages its own loop
- Thread status may get stuck "busy" if worker crashes mid-run
- Dead-lettered messages are never auto-retried -- manual inspection via `/dead-letter` endpoint
- Event publishing during execution: pub/sub (live) + Streams (replay) -- both written per event
- Celery app `Settings()` is instantiated at module level in `celery_app.py` -- env vars must be set before import

## Learnings
- 2026-04-09: celery-aio-pool requires `--pool=custom` flag and `CELERY_CUSTOM_WORKER_POOL` env var set before Celery app import
- 2026-04-09: Celery `bind=True` tasks get `self` as first arg, enabling `self.retry()` for programmatic retries
- 2026-04-09: `task_reject_on_worker_lost` + `task_acks_late` together provide at-least-once delivery on worker crash
- 2026-04-09: TaskPublisher no longer needs Redis as constructor arg -- Celery app is a module-level singleton
