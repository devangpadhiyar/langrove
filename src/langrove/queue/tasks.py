"""Dramatiq task actors for background run execution."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

import dramatiq

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Worker-scoped resources — lazily initialised on the first task invocation.
# Dramatiq's AsyncIO middleware runs all async actors on a single shared event
# loop per worker process, so one asyncio.Lock is sufficient for safe init.
# ---------------------------------------------------------------------------
_state: dict[str, Any] | None = None
_state_lock: asyncio.Lock | None = None


async def _get_state() -> dict[str, Any]:
    """Return worker resources, initialising them on the first call."""
    global _state, _state_lock
    if _state_lock is None:
        _state_lock = asyncio.Lock()
    async with _state_lock:
        if _state is None:
            _state = await _setup_resources()
    return _state


async def _setup_resources() -> dict[str, Any]:
    """Initialise all worker-scoped resources (DB, Redis, checkpointer, …)."""
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
    }


@dramatiq.actor(queue_name="langrove", max_retries=3)
async def handle_run(**payload) -> None:
    """Execute a background graph run.

    Cancellation is handled via a Redis key polled after every streamed event:
    the API sets ``langrove:runs:{run_id}:cancel``; the actor detects it,
    publishes a terminal SSE error event, and returns cleanly (no retry).
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

    # Remove any stale cancel key from a previous run
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
            # --- Cancellation check: poll Redis key set by cancel_run() API ---
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
            logger.info("Run cancelled run_id=%s graph=%s", run_id, graph_id)
            return  # Clean return → Dramatiq ACKs, no retry triggered

        end = end_event()
        await event_broker.publish_redis(run_id, end, event_id=f"{run_id}_event_{event_count + 1}")
        await event_broker.store_event(run_id, end, f"{run_id}_event_{event_count + 1}")

        await run_repo.update_status(uuid.UUID(run_id), "success")
        if thread_id:
            await thread_repo.set_status(uuid.UUID(thread_id), "idle")

        logger.info("Run completed run_id=%s graph=%s events=%d", run_id, graph_id, event_count)

    except Exception as e:
        logger.error(
            "Run failed    run_id=%s graph=%s error=%s: %s",
            run_id,
            graph_id,
            type(e).__name__,
            e,
        )
        err = error_event(str(e), type(e).__name__)
        await event_broker.publish_redis(run_id, err)
        await run_repo.update_status(uuid.UUID(run_id), "error", error=str(e))
        if thread_id:
            await thread_repo.set_status(uuid.UUID(thread_id), "error")
        raise  # Re-raise → Dramatiq Retries middleware re-enqueues; DeadLetterMiddleware
        # writes to langrove:tasks:dead after the last attempt
