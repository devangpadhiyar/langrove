"""Taskiq task functions for background run execution."""

from __future__ import annotations

import asyncio
import logging
import uuid

import orjson
from taskiq import Context, TaskiqDepends

logger = logging.getLogger(__name__)

DEAD_LETTER_STREAM = "langrove:tasks:dead"


async def handle_run(ctx: Context = TaskiqDepends(), **payload) -> None:
    """Execute a background graph run.

    Resources are injected via ctx.state, set up during WORKER_STARTUP:
      redis, executor, event_broker, run_repo, thread_repo, max_delivery_attempts
    """
    from langrove.streaming.formatter import end_event, error_event, metadata_event

    state = ctx.state
    run_id: str = payload["run_id"]
    graph_id: str = payload["graph_id"]
    thread_id: str | None = payload.get("thread_id")
    cancel_key = f"langrove:runs:{run_id}:cancel"

    redis_client = state.redis
    executor = state.executor
    event_broker = state.event_broker
    run_repo = state.run_repo
    thread_repo = state.thread_repo

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
            return  # Normal return → Taskiq ACKs (no retry)

        end = end_event()
        await event_broker.publish_redis(run_id, end, event_id=f"{run_id}_event_{event_count + 1}")
        await event_broker.store_event(run_id, end, f"{run_id}_event_{event_count + 1}")

        await run_repo.update_status(uuid.UUID(run_id), "success")
        if thread_id:
            await thread_repo.set_status(uuid.UUID(thread_id), "idle")

        logger.info("Run completed run_id=%s graph=%s events=%d", run_id, graph_id, event_count)

    except asyncio.CancelledError:
        logger.warning("Run cancelled run_id=%s graph=%s (worker shutting down)", run_id, graph_id)
        await run_repo.update_status(uuid.UUID(run_id), "error", error="Worker cancelled")
        if thread_id:
            await thread_repo.set_status(uuid.UUID(thread_id), "error")
        raise  # No ACK → Taskiq retries (or recovery reclaims via Redis Streams)

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

        # Dead-letter on final attempt (task_retry label set by SimpleRetryMiddleware)
        attempt: int = ctx.message.labels.get("task_retry", 0)
        max_attempts: int = getattr(state, "max_delivery_attempts", 3)
        if attempt >= max_attempts - 1:
            await redis_client.xadd(
                DEAD_LETTER_STREAM,
                {"payload": orjson.dumps(payload).decode()},
            )
            logger.error("Run dead-lettered run_id=%s (exceeded max delivery attempts)", run_id)

        raise  # Raise so Taskiq retries if attempts remain; no-op on last attempt
