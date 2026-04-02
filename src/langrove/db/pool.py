"""asyncpg connection pool lifecycle management."""

from __future__ import annotations

import asyncpg
import orjson


def _jsonb_decoder(val: str):
    # asyncpg passes jsonb as a JSON-encoded string (extra quotes), e.g. '"{}"'
    # First parse strips the outer quotes -> inner JSON string or object
    result = orjson.loads(val)
    # If still a string, it was double-encoded; parse once more
    return orjson.loads(result) if isinstance(result, str) else result


async def _init_connection(conn: asyncpg.Connection) -> None:
    """Register JSON/JSONB codecs so asyncpg returns dicts, not strings."""
    await conn.set_type_codec(
        "jsonb",
        encoder=lambda v: orjson.dumps(v).decode(),
        decoder=_jsonb_decoder,
        schema="pg_catalog",
        format="text",
    )
    await conn.set_type_codec(
        "json",
        encoder=lambda v: orjson.dumps(v).decode(),
        decoder=_jsonb_decoder,
        schema="pg_catalog",
        format="text",
    )


class DatabasePool:
    """Manages the asyncpg connection pool lifecycle."""

    def __init__(self, database_url: str):
        self._url = database_url
        self._pool: asyncpg.Pool | None = None

    @property
    def pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        return self._pool

    async def connect(self) -> None:
        """Create the connection pool."""
        self._pool = await asyncpg.create_pool(
            self._url,
            min_size=2,
            max_size=10,
            init=_init_connection,
        )

    async def disconnect(self) -> None:
        """Close the connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def fetch_one(self, query: str, *args) -> dict | None:
        """Execute a query and return a single row as dict."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, *args)
            return dict(row) if row else None

    async def fetch_all(self, query: str, *args) -> list[dict]:
        """Execute a query and return all rows as dicts."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *args)
            return [dict(r) for r in rows]

    async def execute(self, query: str, *args) -> str:
        """Execute a query and return the status."""
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)
