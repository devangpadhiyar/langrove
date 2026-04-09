"""Celery application factory for Langrove background tasks."""

from __future__ import annotations

import os

from celery import Celery

from langrove.settings import Settings

DEAD_LETTER_STREAM = "langrove:tasks:dead"

_settings = Settings()

# celery-aio-pool: register the async pool via env var before worker starts
os.environ.setdefault("CELERY_CUSTOM_WORKER_POOL", "celery_aio_pool.pool:AsyncIOPool")

app = Celery("langrove")
app.conf.update(
    broker_url=_settings.redis_url,
    # At-least-once delivery: ACK only after task completes
    task_acks_late=True,
    task_reject_on_worker_lost=True,  # re-queue on worker crash
    worker_prefetch_multiplier=1,  # fetch one task at a time (required with acks_late)
    # visibility_timeout MUST be > max task runtime to avoid re-delivery mid-execution
    broker_transport_options={
        "visibility_timeout": _settings.task_timeout_seconds * 2,
    },
    task_serializer="json",
    accept_content=["json"],
    result_backend=None,  # no result storage needed
    task_track_started=True,
    task_default_queue=_settings.queue_name,
    task_routes={
        "langrove.queue.tasks.handle_run": {"queue": _settings.queue_name},
    },
)
