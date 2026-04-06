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
