"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import redis.asyncio as aioredis
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from langrove.api.agents import router as agents_router
from langrove.api.assistants import router as assistants_router
from langrove.api.crons import router as crons_router
from langrove.api.health import router as health_router
from langrove.api.runs import router as runs_router
from langrove.api.store import router as store_router
from langrove.api.store import vfs_router
from langrove.api.threads import router as threads_router
from langrove.config import GraphConfig, load_config
from langrove.db.assistant_repo import AssistantRepository
from langrove.db.pool import DatabasePool
from langrove.exceptions import ConflictError, LangroveError, NotFoundError
from langrove.graph.registry import GraphRegistry
from langrove.services.assistant_service import AssistantService
from langrove.settings import Settings


def create_app(settings: Settings | None = None, config: GraphConfig | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    from dotenv import load_dotenv

    settings = settings or Settings()
    config = config or load_config(settings.config_path)

    # Load the .env specified in langgraph.json (defaults to ".env")
    # Resolved relative to the config file's directory
    if isinstance(config.env, str):
        env_path = Path(settings.config_path).parent / config.env
        load_dotenv(env_path, override=True)
    elif isinstance(config.env, dict):
        import os

        os.environ.update(config.env)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup
        db_pool = DatabasePool(
            settings.database_url,
            min_size=settings.db_pool_min_size,
            max_size=settings.db_pool_max_size,
        )
        await db_pool.connect()
        app.state.db_pool = db_pool

        redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
        app.state.redis = redis_client

        # Load graphs
        registry = GraphRegistry()
        if config.graphs:
            config_dir = Path(settings.config_path).parent
            registry.load_from_config(config.graphs, config_dir if config_dir != Path() else None)
        app.state.graph_registry = registry

        # Setup checkpointer
        from langrove.db.langgraph_pools import setup_checkpointer, setup_store

        checkpointer, cp_pool = await setup_checkpointer(
            settings.database_url, pool_max_size=settings.checkpointer_pool_max_size
        )
        app.state.checkpointer = checkpointer
        app.state.checkpointer_pool = cp_pool

        # Setup LangGraph store (for DeepAgents StoreBackend, etc.)
        store, store_pool = await setup_store(
            settings.database_url, pool_max_size=settings.store_pool_max_size
        )
        app.state.store = store
        app.state.store_pool = store_pool

        app.state.settings = settings
        app.state.config = config

        # Task broker (publisher-only: API enqueues tasks, worker consumes them)
        from taskiq_redis import RedisStreamBroker

        task_broker = RedisStreamBroker(settings.redis_url)
        await task_broker.startup()
        app.state.task_broker = task_broker

        # Auto-create assistants for all graphs defined in langgraph.json
        assistant_service = AssistantService(AssistantRepository(db_pool), registry)
        await assistant_service.auto_create_from_registry()

        yield

        # Shutdown
        await task_broker.shutdown()
        if cp_pool:
            await cp_pool.close()
        if store_pool:
            await store_pool.close()
        await db_pool.disconnect()
        await redis_client.aclose()

    app = FastAPI(
        title="Langrove",
        description="Open-source LangGraph deployment server",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS
    cors = config.http.cors
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors.allow_origins,
        allow_credentials=cors.allow_credentials,
        allow_methods=cors.allow_methods,
        allow_headers=cors.allow_headers,
        expose_headers=cors.expose_headers,
        max_age=cors.max_age,
    )

    # Exception handlers
    @app.exception_handler(NotFoundError)
    async def not_found_handler(request: Request, exc: NotFoundError):
        return JSONResponse(
            status_code=404,
            content={"code": "not_found", "message": str(exc)},
        )

    @app.exception_handler(ConflictError)
    async def conflict_handler(request: Request, exc: ConflictError):
        return JSONResponse(
            status_code=409,
            content={"code": "conflict", "message": str(exc)},
        )

    @app.exception_handler(LangroveError)
    async def langrove_error_handler(request: Request, exc: LangroveError):
        return JSONResponse(
            status_code=500,
            content={"code": "internal_error", "message": str(exc)},
        )

    from langrove.exceptions import ForbiddenError

    @app.exception_handler(ForbiddenError)
    async def forbidden_handler(request: Request, exc: ForbiddenError):
        return JSONResponse(
            status_code=403,
            content={"code": "forbidden", "message": str(exc)},
        )

    # Auth middleware (if configured)
    if config.auth.path:
        from langrove.auth.custom import CustomAuthHandler
        from langrove.auth.middleware import AuthMiddleware

        auth_handler = CustomAuthHandler(config.auth.path)
        app.add_middleware(AuthMiddleware, handler=auth_handler)

    # Register routers
    from langrove.api.dead_letter import router as dead_letter_router

    app.include_router(health_router, tags=["health"])
    app.include_router(assistants_router)
    app.include_router(agents_router)
    app.include_router(threads_router)
    app.include_router(runs_router)
    app.include_router(store_router)
    app.include_router(vfs_router)
    app.include_router(crons_router)
    app.include_router(dead_letter_router)

    return app
