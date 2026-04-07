"""Health check endpoints."""

from __future__ import annotations

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

    Returns task queue depth, pending count, dead-letter depth,
    and per-consumer stats.
    """
    from langrove.queue.consumer import CONSUMER_GROUP, DEAD_LETTER_STREAM
    from langrove.queue.publisher import TASK_STREAM

    redis = request.app.state.redis
    result: dict = {
        "queue_length": 0,
        "pending_total": 0,
        "dead_letter_length": 0,
        "consumers": [],
    }

    # Queue depth
    try:
        stream_info = await redis.xinfo_stream(TASK_STREAM)
        result["queue_length"] = stream_info.get("length", 0)
    except Exception:
        pass

    # Pending tasks and per-consumer stats
    try:
        group_info = await redis.xinfo_groups(TASK_STREAM)
        result["pending_total"] = sum(g.get("pending", 0) for g in group_info)
        for g in group_info:
            if g.get("name") != CONSUMER_GROUP:
                continue
            consumer_info = await redis.xinfo_consumers(TASK_STREAM, CONSUMER_GROUP)
            result["consumers"] = [
                {"name": c["name"], "pending": c["pending"], "idle": c["idle"]}
                for c in consumer_info
            ]
    except Exception:
        pass

    # Dead-letter depth
    try:
        dl_info = await redis.xinfo_stream(DEAD_LETTER_STREAM)
        result["dead_letter_length"] = dl_info.get("length", 0)
    except Exception:
        pass

    return result
