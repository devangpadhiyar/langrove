"""Background worker process for executing graph runs."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
import uuid
from pathlib import Path

import redis.asyncio as aioredis

from langrove.config import load_config
from langrove.db.langgraph_pools import setup_checkpointer, setup_store
from langrove.db.pool import DatabasePool
from langrove.db.run_repo import RunRepository
from langrove.db.thread_repo import ThreadRepository
from langrove.graph.registry import GraphRegistry
from langrove.queue.consumer import TaskConsumer
from langrove.queue.recovery import RecoveryMonitor
from langrove.settings import Settings
from langrove.streaming.broker import EventBroker
from langrove.streaming.executor import RunExecutor
from langrove.streaming.formatter import end_event, error_event, metadata_event

logger = logging.getLogger(__name__)


async def run_worker(worker_id: str | None = None):
    """Main entry point for the worker process."""
    from dotenv import load_dotenv

    settings = Settings()
    config = load_config(settings.config_path)

    # Load .env specified in langgraph.json before anything else
    if isinstance(config.env, str):
        env_path = Path(settings.config_path).parent / config.env
        load_dotenv(env_path, override=True)
    elif isinstance(config.env, dict):
        import os

        os.environ.update(config.env)

    worker_id = worker_id or f"worker-{uuid.uuid4().hex[:8]}"

    logger.info("Langrove Worker '%s' starting...", worker_id)

    # Connect to DB
    db = DatabasePool(
        settings.database_url,
        min_size=settings.db_pool_min_size,
        max_size=settings.db_pool_max_size,
    )
    await db.connect()

    # Connect to Redis
    redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
    registry = GraphRegistry()
    if config.graphs:
        config_dir = Path(settings.config_path).parent
        registry.load_from_config(config.graphs, config_dir if config_dir != Path() else None)

    # Setup checkpointer and store (with pool refs for cleanup)
    checkpointer, cp_pool = await setup_checkpointer(
        settings.database_url, pool_max_size=settings.checkpointer_pool_max_size
    )
    store, store_pool = await setup_store(
        settings.database_url, pool_max_size=settings.store_pool_max_size
    )

    # Create components
    executor = RunExecutor(registry, checkpointer, store=store)
    broker = EventBroker(redis_client, event_stream_ttl_seconds=settings.event_stream_ttl_seconds)
    run_repo = RunRepository(db)
    thread_repo = ThreadRepository(db)
    consumer = TaskConsumer(redis_client, worker_id, concurrency=settings.worker_concurrency)
    recovery = RecoveryMonitor(
        redis_client,
        timeout_ms=settings.task_timeout_seconds * 1000,
        max_attempts=settings.max_delivery_attempts,
        interval_seconds=settings.recovery_interval_seconds,
    )

    async def handle_task(payload: dict) -> None:
        """Execute a background run task."""
        run_id = payload["run_id"]
        graph_id = payload["graph_id"]
        thread_id = payload.get("thread_id")
        cancel_key = f"langrove:runs:{run_id}:cancel"

        logger.info("Run started   run_id=%s graph=%s thread=%s", run_id, graph_id, thread_id)

        # Remove any stale cancel key from a previous run (defensive; UUIDs don't repeat)
        await redis_client.delete(cancel_key)

        await run_repo.update_status(uuid.UUID(run_id), "running")
        if thread_id:
            await thread_repo.set_status(uuid.UUID(thread_id), "busy")

        event_count = 0
        cancelled = False
        try:
            # Publish metadata event
            meta = metadata_event(run_id)
            await broker.publish_redis(run_id, meta, event_id=f"{run_id}_event_0")
            await broker.store_event(run_id, meta, f"{run_id}_event_0")

            # Execute graph -- poll cancel key after each event
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
                    break  # triggers aclosing() cleanup on the generator

                event_count += 1
                event_id = f"{run_id}_event_{event_count}"
                await broker.publish_redis(run_id, part, event_id=event_id)
                await broker.store_event(run_id, part, event_id)

            if cancelled:
                # Publish terminal error event so connected SSE clients close
                err = error_event("Run was cancelled", "RunCancelled")
                await broker.publish_redis(
                    run_id, err, event_id=f"{run_id}_event_{event_count + 1}"
                )
                await broker.store_event(run_id, err, f"{run_id}_event_{event_count + 1}")
                await redis_client.delete(cancel_key)
                # Status + thread already updated by cancel_run() in the API — don't overwrite
                logger.info("Run cancelled run_id=%s graph=%s", run_id, graph_id)
                return  # Normal return → _handle_one will XACK (no retry)

            # Publish end event
            end = end_event()
            await broker.publish_redis(run_id, end, event_id=f"{run_id}_event_{event_count + 1}")
            await broker.store_event(run_id, end, f"{run_id}_event_{event_count + 1}")

            await run_repo.update_status(uuid.UUID(run_id), "success")
            if thread_id:
                await thread_repo.set_status(uuid.UUID(thread_id), "idle")

            logger.info(
                "Run completed run_id=%s graph=%s events=%d", run_id, graph_id, event_count
            )

        except asyncio.CancelledError:
            logger.warning(
                "Run cancelled run_id=%s graph=%s (worker shutting down)", run_id, graph_id
            )
            await run_repo.update_status(uuid.UUID(run_id), "error", error="Worker cancelled")
            if thread_id:
                await thread_repo.set_status(uuid.UUID(thread_id), "error")
            raise  # No XACK — recovery will reclaim

        except Exception as e:
            logger.error(
                "Run failed    run_id=%s graph=%s error=%s: %s",
                run_id,
                graph_id,
                type(e).__name__,
                e,
            )
            err = error_event(str(e), type(e).__name__)
            await broker.publish_redis(run_id, err)
            await run_repo.update_status(uuid.UUID(run_id), "error", error=str(e))
            if thread_id:
                await thread_repo.set_status(uuid.UUID(thread_id), "error")
            raise  # No XACK — recovery will retry

    async def on_dead_letter(run_id: str | None) -> None:
        """Handle poison messages."""
        if run_id:
            await run_repo.update_status(
                uuid.UUID(run_id), "error", error="Max delivery attempts exceeded"
            )
            logger.error("Run dead-lettered run_id=%s (exceeded max delivery attempts)", run_id)

    logger.info(
        "Worker '%s' ready (concurrency=%d). Waiting for tasks...",
        worker_id,
        settings.worker_concurrency,
    )

    # Graceful shutdown via SIGTERM/SIGINT.
    # First signal: drain in-flight tasks. Second signal: abort immediately.
    shutdown_event = asyncio.Event()
    force_quit = False

    def _on_signal():
        nonlocal force_quit
        if shutdown_event.is_set():
            force_quit = True
            logger.warning(
                "Force quit — cancelling %d in-flight task(s)...", len(consumer.in_flight_tasks)
            )
            for t in consumer.in_flight_tasks:
                t.cancel()
        else:
            logger.info(
                "Worker '%s' shutting down gracefully (signal again to force)...", worker_id
            )
            shutdown_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _on_signal)

    try:
        main_task = asyncio.ensure_future(
            asyncio.gather(
                consumer.run_loop(handle_task),
                recovery.run(on_reclaim=on_dead_letter),
            )
        )
        shutdown_wait = asyncio.ensure_future(shutdown_event.wait())

        await asyncio.wait(
            [main_task, shutdown_wait],
            return_when=asyncio.FIRST_COMPLETED,
        )

        # Cancel the consumer/recovery loops
        main_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await main_task

        # Drain in-flight tasks (unless force-quit already cancelled them)
        in_flight = consumer.in_flight_tasks
        if in_flight and not force_quit:
            logger.info("Waiting for %d in-flight task(s) to finish...", len(in_flight))
            await asyncio.wait(in_flight, timeout=settings.shutdown_timeout_seconds)

    finally:
        logger.info("Worker '%s' stopped.", worker_id)
        if cp_pool:
            await cp_pool.close()
        if store_pool:
            await store_pool.close()
        await db.disconnect()
        await redis_client.aclose()
