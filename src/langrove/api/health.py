"""Health check endpoints."""

from __future__ import annotations

import contextlib

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/ok")
async def ok():
    """Simple liveness check."""
    return {"ok": True}


@router.get("/health")
async def health(request: Request):
    """Health check -- verifies database and Redis connectivity."""
    checks = {}

    # Check database
    try:
        db = request.app.state.db_pool
        await db.fetch_one("SELECT 1")
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {e}"

    # Check Redis
    try:
        redis = request.app.state.redis
        await redis.ping()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {e}"

    all_ok = all(v == "ok" for v in checks.values())
    return {"status": "healthy" if all_ok else "unhealthy", "checks": checks}


@router.get("/info")
async def info(request: Request):
    """Server information."""
    registry = request.app.state.graph_registry
    return {
        "name": "langrove",
        "version": "0.1.0",
        "graphs": [g.graph_id for g in registry.list_graphs()],
    }


@router.get("/metrics")
async def metrics(request: Request):
    """Queue metrics for monitoring and autoscaling (HPA).

    Returns Celery queue length and dead-letter depth.
    """
    from langrove.queue.celery_app import DEAD_LETTER_STREAM
    from langrove.settings import Settings

    settings = Settings()
    redis = request.app.state.redis
    result: dict = {
        "queue_length": 0,
        "dead_letter_length": 0,
    }

    # Celery uses a Redis list for the queue (key = queue name)
    with contextlib.suppress(Exception):
        result["queue_length"] = await redis.llen(settings.queue_name)

    # Dead-letter depth (still a Redis Stream)
    with contextlib.suppress(Exception):
        dl_info = await redis.xinfo_stream(DEAD_LETTER_STREAM)
        result["dead_letter_length"] = dl_info.get("length", 0)

    return result
