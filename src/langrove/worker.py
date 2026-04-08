"""Background worker process -- Taskiq with Redis Streams (at-least-once delivery)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
from pathlib import Path

logger = logging.getLogger(__name__)


async def run_worker(worker_id: str | None = None):
    """Main entry point for the Taskiq worker process."""
    from dotenv import load_dotenv
    from taskiq import TaskiqEvents, TaskiqState
    from taskiq.middlewares.retry_middleware import SimpleRetryMiddleware
    from taskiq_redis import RedisStreamBroker

    from langrove.config import load_config
    from langrove.settings import Settings

    settings = Settings()
    config = load_config(settings.config_path)

    # Load .env specified in langgraph.json before anything else
    if isinstance(config.env, str):
        env_path = Path(settings.config_path).parent / config.env
        load_dotenv(env_path, override=True)
    elif isinstance(config.env, dict):
        import os

        os.environ.update(config.env)

    logger.info("Langrove Worker starting (Taskiq / Redis Streams)...")

    # --- Broker: Redis Streams gives native XREADGROUP/XACK late-ack ---
    broker = RedisStreamBroker(settings.redis_url).with_middlewares(
        SimpleRetryMiddleware(default_retry_count=settings.max_delivery_attempts),
    )

    # --- Startup: initialise all worker-scoped resources into broker state ---
    @broker.on_event(TaskiqEvents.WORKER_STARTUP)
    async def startup(state: TaskiqState) -> None:
        import redis.asyncio as aioredis

        from langrove.db.langgraph_pools import setup_checkpointer, setup_store
        from langrove.db.pool import DatabasePool
        from langrove.db.run_repo import RunRepository
        from langrove.db.thread_repo import ThreadRepository
        from langrove.graph.registry import GraphRegistry
        from langrove.streaming.broker import EventBroker
        from langrove.streaming.executor import RunExecutor

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

        state.db = db
        state.redis = redis_client
        state.executor = RunExecutor(registry, checkpointer, store=store)
        state.event_broker = EventBroker(
            redis_client, event_stream_ttl_seconds=settings.event_stream_ttl_seconds
        )
        state.run_repo = RunRepository(db)
        state.thread_repo = ThreadRepository(db)
        state.cp_pool = cp_pool
        state.store_pool = store_pool
        state.max_delivery_attempts = settings.max_delivery_attempts

        logger.info("Worker resources initialised (concurrency=%d)", settings.worker_concurrency)

    # --- Shutdown: clean up all worker-scoped resources ---
    @broker.on_event(TaskiqEvents.WORKER_SHUTDOWN)
    async def shutdown(state: TaskiqState) -> None:
        if getattr(state, "cp_pool", None):
            await state.cp_pool.close()
        if getattr(state, "store_pool", None):
            await state.store_pool.close()
        if getattr(state, "db", None):
            await state.db.disconnect()
        if getattr(state, "redis", None):
            await state.redis.aclose()
        logger.info("Worker resources cleaned up.")

    # Register task function with retry settings
    from langrove.queue.tasks import handle_run

    broker.register_task(
        handle_run,
        task_name="handle_run",
        retry_on_error=True,
        max_retries=settings.max_delivery_attempts,
        timeout=settings.task_timeout_seconds,
    )

    # --- Graceful shutdown via SIGTERM/SIGINT ---
    # First signal: drain in-flight tasks. Second signal: force quit.
    shutdown_event = asyncio.Event()
    force_quit = False

    def _on_signal() -> None:
        nonlocal force_quit
        if shutdown_event.is_set():
            force_quit = True
            logger.warning("Force quit — aborting worker immediately.")
        else:
            logger.info("Worker shutting down gracefully (signal again to force)...")
            shutdown_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _on_signal)

    await broker.startup()

    from taskiq.worker.receiver import Receiver

    receiver = Receiver(
        broker=broker,
        max_async_tasks=settings.worker_concurrency,
    )

    try:
        listen_task = asyncio.ensure_future(receiver.listen())
        shutdown_wait = asyncio.ensure_future(shutdown_event.wait())

        # Run until a shutdown signal or the receiver stops on its own
        await asyncio.wait(
            [listen_task, shutdown_wait],
            return_when=asyncio.FIRST_COMPLETED,
        )

        # Cancel the receiver loop
        listen_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await listen_task

    finally:
        await broker.shutdown()
        logger.info("Worker stopped.")
