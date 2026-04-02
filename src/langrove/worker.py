"""Background worker process for executing graph runs."""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Any

import redis.asyncio as aioredis

from langrove.config import load_config
from langrove.db.pool import DatabasePool
from langrove.db.run_repo import RunRepository
from langrove.db.thread_repo import ThreadRepository
from langrove.graph.registry import GraphRegistry
from langrove.models.common import StreamPart
from langrove.queue.consumer import TaskConsumer
from langrove.queue.recovery import RecoveryMonitor
from langrove.settings import Settings
from langrove.streaming.broker import EventBroker
from langrove.streaming.executor import RunExecutor
from langrove.streaming.formatter import end_event, error_event, metadata_event


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

    print(f"Langrove Worker '{worker_id}' starting...")

    # Connect to DB
    db = DatabasePool(settings.database_url)
    await db.connect()

    # Connect to Redis
    redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
    registry = GraphRegistry()
    if config.graphs:
        config_dir = Path(settings.config_path).parent
        registry.load_from_config(config.graphs, config_dir if config_dir != Path() else None)

    # Setup checkpointer
    checkpointer = await _setup_checkpointer(settings.database_url)

    # Create components
    executor = RunExecutor(registry, checkpointer)
    broker = EventBroker(redis_client)
    run_repo = RunRepository(db)
    thread_repo = ThreadRepository(db)
    consumer = TaskConsumer(redis_client, worker_id)
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

        print(f"Executing run {run_id} (graph: {graph_id})")

        await run_repo.update_status(uuid.UUID(run_id), "running")
        if thread_id:
            await thread_repo.set_status(uuid.UUID(thread_id), "busy")

        event_count = 0
        try:
            # Publish metadata event
            meta = metadata_event(run_id)
            await broker.publish_redis(run_id, meta, event_id=f"{run_id}_event_0")
            await broker.store_event(run_id, meta, f"{run_id}_event_0")

            # Execute graph
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
            ):
                event_count += 1
                event_id = f"{run_id}_event_{event_count}"
                await broker.publish_redis(run_id, part, event_id=event_id)
                await broker.store_event(run_id, part, event_id)

            # Publish end event
            end = end_event()
            await broker.publish_redis(run_id, end, event_id=f"{run_id}_event_{event_count + 1}")
            await broker.store_event(run_id, end, f"{run_id}_event_{event_count + 1}")

            await run_repo.update_status(uuid.UUID(run_id), "success")
            if thread_id:
                await thread_repo.set_status(uuid.UUID(thread_id), "idle")

            print(f"Run {run_id} completed ({event_count} events)")

        except Exception as e:
            err = error_event(str(e), type(e).__name__)
            await broker.publish_redis(run_id, err)
            await run_repo.update_status(uuid.UUID(run_id), "error", error=str(e))
            if thread_id:
                await thread_repo.set_status(uuid.UUID(thread_id), "error")
            raise  # Re-raise so consumer doesn't ack

    async def on_dead_letter(run_id: str | None) -> None:
        """Handle poison messages."""
        if run_id:
            await run_repo.update_status(uuid.UUID(run_id), "error", error="Max delivery attempts exceeded")
            print(f"Run {run_id} dead-lettered")

    print(f"Worker '{worker_id}' ready. Waiting for tasks...")

    try:
        # Run consumer and recovery monitor concurrently
        await asyncio.gather(
            consumer.run_loop(handle_task),
            recovery.run(on_reclaim=on_dead_letter),
        )
    except KeyboardInterrupt:
        pass
    finally:
        print(f"Worker '{worker_id}' shutting down...")
        await db.disconnect()
        await redis_client.aclose()


async def _setup_checkpointer(database_url: str) -> Any:
    """Setup the LangGraph PostgreSQL checkpointer backed by a connection pool."""
    try:
        from psycopg_pool import AsyncConnectionPool
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        pool = AsyncConnectionPool(
            conninfo=database_url,
            max_size=5,
            kwargs={"autocommit": True, "prepare_threshold": 0},
            open=False,
        )
        await pool.open()
        checkpointer = AsyncPostgresSaver(conn=pool)
        await checkpointer.setup()
        return checkpointer
    except ImportError:
        return None
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("Worker checkpointer setup failed: %s", e)
        return None
