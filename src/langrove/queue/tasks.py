"""Celery task actors for background run execution."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from typing import Any

import orjson
from celery import Task
from celery.exceptions import MaxRetriesExceededError
from celery.signals import worker_process_shutdown

from langrove.queue.celery_app import DEAD_LETTER_STREAM, app

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Worker-scoped resources -- initialised once per worker process via lazy
# init on first task. celery-aio-pool runs all async tasks on a single shared
# event loop per worker process, so one asyncio.Lock is safe.
# ---------------------------------------------------------------------------
_state: dict[str, Any] | None = None
_state_lock: asyncio.Lock | None = None


@worker_process_shutdown.connect
def _shutdown_worker_resources(**kwargs) -> None:
    """Attempt to close resources cleanly on worker process exit."""
    global _state
    if _state is None:
        return
    loop = asyncio.get_event_loop()
    if loop.is_running():
        loop.create_task(_teardown_resources(_state))
    _state = None


async def _teardown_resources(state: dict) -> None:
    with contextlib.suppress(Exception):
        await state["db"].disconnect()
    with contextlib.suppress(Exception):
        await state["redis"].aclose()
    with contextlib.suppress(Exception):
        if state.get("cp_pool"):
            await state["cp_pool"].close()
    with contextlib.suppress(Exception):
        if state.get("store_pool"):
            await state["store_pool"].close()


async def _get_state() -> dict[str, Any]:
    """Return worker resources, initialising on first call."""
    global _state, _state_lock

    if _state_lock is None:
        _state_lock = asyncio.Lock()

    async with _state_lock:
        if _state is None:
            _state = await _setup_resources()

    return _state


async def _setup_resources() -> dict[str, Any]:
    """Initialise all worker-scoped async resources."""
    from pathlib import Path

    import redis.asyncio as aioredis

    from langrove.config import load_config
    from langrove.db.langgraph_pools import setup_checkpointer, setup_store
    from langrove.db.pool import DatabasePool
    from langrove.db.run_repo import RunRepository
    from langrove.db.thread_repo import ThreadRepository
    from langrove.graph.registry import GraphRegistry
    from langrove.settings import Settings
    from langrove.streaming.broker import EventBroker
    from langrove.streaming.executor import RunExecutor

    settings = Settings()
    config = load_config(settings.config_path)

    db = DatabasePool(
        settings.database_url,
        min_size=settings.db_pool_min_size,
        max_size=settings.db_pool_max_size,
    )
    await db.connect()

    redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)

    registry = GraphRegistry()
    if config.graphs:
        config_dir = Path(settings.config_path).parent
        registry.load_from_config(config.graphs, config_dir if config_dir != Path() else None)

    checkpointer, cp_pool = await setup_checkpointer(
        settings.database_url, pool_max_size=settings.checkpointer_pool_max_size
    )
    store, store_pool = await setup_store(
        settings.database_url, pool_max_size=settings.store_pool_max_size
    )

    logger.info("Worker resources initialised")
    return {
        "db": db,
        "redis": redis_client,
        "executor": RunExecutor(registry, checkpointer, store=store),
        "event_broker": EventBroker(
            redis_client, event_stream_ttl_seconds=settings.event_stream_ttl_seconds
        ),
        "run_repo": RunRepository(db),
        "thread_repo": ThreadRepository(db),
        "cp_pool": cp_pool,
        "store_pool": store_pool,
        "settings": settings,
    }


async def _write_dead_letter(payload: dict) -> None:
    """Write a failed task payload to the dead-letter Redis stream."""
    import redis as sync_redis

    from langrove.settings import Settings

    settings = Settings()
    r = sync_redis.from_url(settings.redis_url, decode_responses=True)
    try:
        r.xadd(DEAD_LETTER_STREAM, {"payload": orjson.dumps(payload).decode()})
        logger.error("Run dead-lettered run_id=%s", payload.get("run_id", "?"))
    except Exception:
        logger.exception("Failed to write dead-letter entry")
    finally:
        r.close()


@app.task(
    bind=True,
    name="langrove.queue.tasks.handle_run",
    acks_late=True,
    reject_on_worker_lost=True,
    max_retries=3,
    default_retry_delay=30,
)
async def handle_run(self: Task, **payload) -> None:
    """Execute a background graph run.

    Cancellation is via a Redis key polled after every streamed event:
    API sets ``langrove:runs:{run_id}:cancel``; actor detects it and returns
    cleanly (no retry triggered).

    On exception: Celery retries up to max_retries, then dead-letters.
    """
    from langrove.streaming.formatter import end_event, error_event, metadata_event

    state = await _get_state()

    run_id: str = payload["run_id"]
    graph_id: str = payload["graph_id"]
    thread_id: str | None = payload.get("thread_id")
    cancel_key = f"langrove:runs:{run_id}:cancel"

    redis_client = state["redis"]
    executor = state["executor"]
    event_broker = state["event_broker"]
    run_repo = state["run_repo"]
    thread_repo = state["thread_repo"]

    logger.info("Run started   run_id=%s graph=%s thread=%s", run_id, graph_id, thread_id)

    await redis_client.delete(cancel_key)
    await run_repo.update_status(uuid.UUID(run_id), "running")
    if thread_id:
        await thread_repo.set_status(uuid.UUID(thread_id), "busy")

    event_count = 0
    cancelled = False

    try:
        meta = metadata_event(run_id)
        await event_broker.publish_redis(run_id, meta, event_id=f"{run_id}_event_0")
        await event_broker.store_event(run_id, meta, f"{run_id}_event_0")

        async for part in executor.execute_stream(
            graph_id,
            input=payload.get("input"),
            command=payload.get("command"),
            config=payload.get("config"),
            thread_id=thread_id,
            stream_mode=payload.get("stream_mode", "values"),
            stream_subgraphs=payload.get("stream_subgraphs", False),
            interrupt_before=payload.get("interrupt_before"),
            interrupt_after=payload.get("interrupt_after"),
            checkpoint_id=payload.get("checkpoint_id"),
            auth_user=payload.get("auth_user"),
        ):
            if await redis_client.exists(cancel_key):
                cancelled = True
                break

            event_count += 1
            event_id = f"{run_id}_event_{event_count}"
            await event_broker.publish_redis(run_id, part, event_id=event_id)
            await event_broker.store_event(run_id, part, event_id)

        if cancelled:
            err = error_event("Run was cancelled", "RunCancelled")
            await event_broker.publish_redis(
                run_id, err, event_id=f"{run_id}_event_{event_count + 1}"
            )
            await event_broker.store_event(run_id, err, f"{run_id}_event_{event_count + 1}")
            await redis_client.delete(cancel_key)
            logger.info("Run cancelled run_id=%s", run_id)
            return  # Clean return -- Celery ACKs, no retry triggered

        end = end_event()
        await event_broker.publish_redis(run_id, end, event_id=f"{run_id}_event_{event_count + 1}")
        await event_broker.store_event(run_id, end, f"{run_id}_event_{event_count + 1}")

        await run_repo.update_status(uuid.UUID(run_id), "success")
        if thread_id:
            await thread_repo.set_status(uuid.UUID(thread_id), "idle")

        logger.info("Run completed run_id=%s graph=%s events=%d", run_id, graph_id, event_count)

    except Exception as exc:
        logger.error("Run failed run_id=%s error=%s: %s", run_id, type(exc).__name__, exc)

        err = error_event(str(exc), type(exc).__name__)
        with contextlib.suppress(Exception):
            await event_broker.publish_redis(run_id, err)

        await run_repo.update_status(uuid.UUID(run_id), "error", error=str(exc))
        if thread_id:
            await thread_repo.set_status(uuid.UUID(thread_id), "error")

        try:
            raise self.retry(exc=exc, countdown=30)
        except MaxRetriesExceededError:
            # All retries exhausted -- dead-letter
            await _write_dead_letter(payload)
            raise  # Re-raise so Celery marks task as FAILURE (no further retry)
