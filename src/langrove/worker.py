"""Background worker process -- Celery with celery-aio-pool (asyncio tasks)."""

from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)


def run_worker(
    worker_id: str | None = None,
    queues: list[str] | None = None,
) -> None:
    """Start the Celery worker. Blocks until SIGTERM/SIGINT."""
    from dotenv import load_dotenv

    from langrove.config import load_config
    from langrove.settings import Settings

    settings = Settings()
    config = load_config(settings.config_path)

    # Load .env before anything accesses env-dependent settings
    if isinstance(config.env, str):
        env_path = Path(settings.config_path).parent / config.env
        load_dotenv(env_path, override=True)
    elif isinstance(config.env, dict):
        os.environ.update(config.env)

    effective_id = worker_id or f"worker-{uuid.uuid4().hex[:8]}"
    effective_queues = queues or [settings.queue_name]

    logger.info(
        "Langrove Worker starting worker_id=%s queues=%s (Celery / AsyncIO pool)...",
        effective_id,
        effective_queues,
    )

    # Ensure celery-aio-pool is selected
    os.environ.setdefault("CELERY_CUSTOM_WORKER_POOL", "celery_aio_pool.pool:AsyncIOPool")

    import langrove.queue.tasks  # noqa: F401 -- registers task with Celery app
    from langrove.queue.celery_app import app

    argv = [
        "worker",
        f"--hostname={effective_id}@%h",
        "--pool=custom",  # selects celery-aio-pool
        f"--queues={','.join(effective_queues)}",
        f"--concurrency={settings.worker_concurrency}",
        f"--loglevel={logging.getLevelName(logger.parent.level).lower() if logger.parent else 'info'}",
        "--without-gossip",  # reduces Redis chatter
        "--without-mingle",  # skip startup sync between workers
        "--without-heartbeat",  # reduce idle Redis traffic
    ]

    logger.info("Starting Celery worker with args: %s", argv)
    app.worker_main(argv=argv)
