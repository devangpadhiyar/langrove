"""Background worker process -- Dramatiq with Redis broker (at-least-once delivery).

Dramatiq's RedisBroker moves messages to a processing list atomically via
RPOPLPUSH/BLMOVE.  Messages are only deleted from that list after the actor
function returns cleanly, giving at-least-once delivery semantics on worker
crash.  Retries and dead-lettering are handled by the Retries middleware and
our custom DeadLetterMiddleware (see queue/broker.py).
"""

from __future__ import annotations

import asyncio
import logging
import signal
from pathlib import Path

logger = logging.getLogger(__name__)


async def run_worker(
    worker_id: str | None = None,
    queues: list[str] | None = None,
):
    """Main entry point for the Dramatiq worker process."""
    from dotenv import load_dotenv

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

    effective_id = worker_id or "worker-default"
    logger.info(
        "Langrove Worker starting worker_id=%s queues=%s (Dramatiq / Redis)...",
        effective_id,
        queues or "all",
    )

    # 1. Set up the global Dramatiq broker BEFORE importing tasks so that the
    #    @dramatiq.actor decorator attaches to the correct broker instance.
    from langrove.queue.broker import setup_broker

    setup_broker(
        settings.redis_url,
        max_delivery_attempts=settings.max_delivery_attempts,
        task_timeout_ms=settings.task_timeout_seconds * 1000,
    )

    # 2. Import tasks (registers actors with the broker just configured above).
    import dramatiq

    from langrove.queue.tasks import handle_run  # noqa: F401

    # 3. Create the Dramatiq worker.
    #    worker_threads controls concurrency; each thread handles one message
    #    at a time. With AsyncIO middleware, all async actors share one event
    #    loop, so effective async concurrency = worker_threads.
    broker = dramatiq.get_broker()
    worker = dramatiq.Worker(
        broker,
        queues=queues or None,  # None → process all registered queues
        worker_threads=settings.worker_concurrency,
        worker_timeout=settings.worker_timeout_ms,
    )

    # --- Graceful shutdown via SIGTERM/SIGINT (two-phase) ---
    # First signal: stop accepting new tasks, wait for in-flight to finish.
    # Second signal: force-stop immediately.
    shutdown_event = asyncio.Event()
    force_quit = False

    def _on_signal() -> None:
        nonlocal force_quit
        if shutdown_event.is_set():
            force_quit = True
            logger.warning("Force quit — stopping worker immediately.")
            worker.stop(timeout=0)  # timeout=0 → joins threads with 0 s wait (returns immediately)
        else:
            logger.info("Worker shutting down gracefully (signal again to force)...")
            shutdown_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _on_signal)

    worker.start()
    logger.info(
        "Worker ready worker_id=%s (threads=%d, worker_timeout=%dms, queues=%s). Waiting for tasks...",
        effective_id,
        settings.worker_concurrency,
        settings.worker_timeout_ms,
        queues or "all",
    )

    try:
        # Block until a shutdown signal arrives
        await shutdown_event.wait()

        logger.info(
            "Stopping worker, draining in-flight tasks (timeout=%ds)...",
            settings.shutdown_timeout_seconds,
        )
        # Worker.stop(timeout=ms) joins every consumer + worker thread with
        # that per-thread timeout, then returns.  Run in executor so the
        # asyncio event loop stays unblocked during the drain.
        await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: worker.stop(timeout=settings.shutdown_timeout_seconds * 1000),
        )
    finally:
        logger.info("Worker stopped.")
