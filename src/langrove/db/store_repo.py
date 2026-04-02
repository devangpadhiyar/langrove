"""Repository for store item CRUD operations."""

from __future__ import annotations

from typing import Any

import orjson

from langrove.db.pool import DatabasePool
from langrove.exceptions import NotFoundError


class StoreRepository:
    """Data access for the store_items table."""

    def __init__(self, db: DatabasePool):
        self._db = db

    async def put(self, namespace: list[str], key: str, value: Any) -> None:
        """Upsert a store item."""
        await self._db.execute(
            """
            INSERT INTO store_items (namespace, key, value, updated_at)
            VALUES ($1, $2, $3::jsonb, NOW())
            ON CONFLICT (namespace, key)
            DO UPDATE SET value = $3::jsonb, updated_at = NOW()
            """,
            namespace,
            key,
            orjson.dumps(value).decode(),
        )

    async def get(self, namespace: list[str], key: str) -> dict | None:
        """Get a store item by namespace + key."""
        row = await self._db.fetch_one(
            "SELECT * FROM store_items WHERE namespace = $1 AND key = $2",
            namespace,
            key,
        )
        return dict(row) if row else None

    async def delete(self, namespace: list[str], key: str) -> None:
        """Delete a store item."""
        result = await self._db.execute(
            "DELETE FROM store_items WHERE namespace = $1 AND key = $2",
            namespace,
            key,
        )
        if result == "DELETE 0":
            raise NotFoundError("store_item", f"{namespace}/{key}")

    async def search(
        self,
        *,
        namespace_prefix: list[str] | None = None,
        filter: dict[str, Any] | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> list[dict]:
        """Search store items."""
        conditions = []
        args = []
        idx = 1

        if namespace_prefix:
            conditions.append(f"namespace[1:{len(namespace_prefix)}] = ${idx}")
            args.append(namespace_prefix)
            idx += 1

        if filter:
            conditions.append(f"value @> ${idx}::jsonb")
            args.append(orjson.dumps(filter).decode())
            idx += 1

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        args.extend([limit, offset])

        rows = await self._db.fetch_all(
            f"SELECT * FROM store_items {where} ORDER BY created_at DESC LIMIT ${idx} OFFSET ${idx + 1}",
            *args,
        )
        return [dict(r) for r in rows]

    async def list_namespaces(
        self,
        *,
        prefix: list[str] | None = None,
        suffix: list[str] | None = None,
        max_depth: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[list[str]]:
        """List distinct namespaces."""
        conditions = []
        args = []
        idx = 1

        if prefix:
            conditions.append(f"namespace[1:{len(prefix)}] = ${idx}")
            args.append(prefix)
            idx += 1

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        if max_depth:
            select = f"DISTINCT namespace[1:{max_depth}]"
        else:
            select = "DISTINCT namespace"

        args.extend([limit, offset])

        rows = await self._db.fetch_all(
            f"SELECT {select} as namespace FROM store_items {where} LIMIT ${idx} OFFSET ${idx + 1}",
            *args,
        )
        return [r["namespace"] for r in rows]
