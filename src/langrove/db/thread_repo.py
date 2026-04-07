"""Repository for thread CRUD operations."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from langrove.db.pool import DatabasePool
from langrove.exceptions import ConflictError, NotFoundError


class ThreadRepository:
    """Data access for the threads table."""

    def __init__(self, db: DatabasePool):
        self._db = db

    async def create(
        self,
        *,
        thread_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
        if_exists: str = "raise",
    ) -> dict:
        """Create a new thread."""
        tid = thread_id or uuid4()

        # Check if exists
        if thread_id:
            existing = await self._db.fetch_one("SELECT * FROM threads WHERE thread_id = $1", tid)
            if existing:
                if if_exists == "do_nothing":
                    return self._normalize(existing)
                raise ConflictError(f"Thread '{tid}' already exists")

        row = await self._db.fetch_one(
            """
            INSERT INTO threads (thread_id, metadata_)
            VALUES ($1, $2)
            RETURNING *
            """,
            tid,
            metadata or {},
        )
        return self._normalize(row)

    async def get(self, thread_id: UUID) -> dict:
        """Get a thread by ID."""
        row = await self._db.fetch_one("SELECT * FROM threads WHERE thread_id = $1", thread_id)
        if row is None:
            raise NotFoundError("thread", str(thread_id))
        return self._normalize(row)

    async def update(self, thread_id: UUID, metadata: dict[str, Any] | None = None) -> dict:
        """Update thread metadata."""
        if metadata is None:
            return await self.get(thread_id)

        row = await self._db.fetch_one(
            """
            UPDATE threads SET metadata_ = $1, updated_at = NOW()
            WHERE thread_id = $2
            RETURNING *
            """,
            metadata,
            thread_id,
        )
        if row is None:
            raise NotFoundError("thread", str(thread_id))
        return self._normalize(row)

    async def delete(self, thread_id: UUID) -> None:
        """Delete a thread."""
        result = await self._db.execute("DELETE FROM threads WHERE thread_id = $1", thread_id)
        if result == "DELETE 0":
            raise NotFoundError("thread", str(thread_id))

    async def search(
        self,
        *,
        metadata: dict[str, Any] | None = None,
        status: str | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> list[dict]:
        """Search threads."""
        conditions = []
        args = []
        idx = 1

        if status is not None:
            conditions.append(f"status = ${idx}")
            args.append(status)
            idx += 1

        if metadata:
            conditions.append(f"metadata_ @> ${idx}")
            args.append(metadata)
            idx += 1

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        args.extend([limit, offset])

        rows = await self._db.fetch_all(
            f"SELECT * FROM threads {where} ORDER BY created_at DESC LIMIT ${idx} OFFSET ${idx + 1}",
            *args,
        )
        return [self._normalize(r) for r in rows]

    async def copy(self, thread_id: UUID) -> dict:
        """Copy a thread (creates a new thread with same metadata)."""
        source = await self.get(thread_id)
        return await self.create(metadata=source.get("metadata", {}))

    async def set_status(self, thread_id: UUID, status: str) -> None:
        """Update thread status."""
        await self._db.execute(
            "UPDATE threads SET status = $1, updated_at = NOW() WHERE thread_id = $2",
            status,
            thread_id,
        )

    @staticmethod
    def _normalize(row: dict | None) -> dict:
        if row is None:
            return {}
        result = dict(row)
        if "metadata_" in result:
            result["metadata"] = result.pop("metadata_")
        return result
