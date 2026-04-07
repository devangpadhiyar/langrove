"""Shared setup for LangGraph checkpointer and store psycopg pools."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def setup_checkpointer(database_url: str, *, pool_max_size: int = 5) -> tuple[Any, Any]:
    """Setup the LangGraph PostgreSQL checkpointer backed by a connection pool.

    Returns (checkpointer, pool). Both are None on failure.
    """
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from psycopg_pool import AsyncConnectionPool

        pool = AsyncConnectionPool(
            conninfo=database_url,
            max_size=pool_max_size,
            kwargs={"autocommit": True, "prepare_threshold": 0},
            open=False,
        )
        await pool.open()
        checkpointer = AsyncPostgresSaver(conn=pool)
        await checkpointer.setup()
        return checkpointer, pool
    except ImportError:
        return None, None
    except Exception as e:
        logger.warning("Checkpointer setup failed: %s", e)
        return None, None


async def setup_store(database_url: str, *, pool_max_size: int = 5) -> tuple[Any, Any]:
    """Setup the LangGraph PostgreSQL store backed by a connection pool.

    Returns (store, pool). Both are None on failure.
    """
    try:
        from langgraph.store.postgres import AsyncPostgresStore
        from psycopg_pool import AsyncConnectionPool

        pool = AsyncConnectionPool(
            conninfo=database_url,
            max_size=pool_max_size,
            kwargs={"autocommit": True, "prepare_threshold": 0},
            open=False,
        )
        await pool.open()
        store = AsyncPostgresStore(conn=pool)
        await store.setup()
        return store, pool
    except ImportError:
        return None, None
    except Exception as e:
        logger.warning("Store setup failed: %s", e)
        return None, None
