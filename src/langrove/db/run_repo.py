"""Repository for run CRUD operations."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import orjson

from langrove.db.pool import DatabasePool
from langrove.exceptions import NotFoundError


class RunRepository:
    """Data access for the runs table."""

    def __init__(self, db: DatabasePool):
        self._db = db

    async def create(
        self,
        *,
        assistant_id: UUID,
        thread_id: UUID | None = None,
        input: Any | None = None,
        kwargs: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        multitask_strategy: str = "reject",
    ) -> dict:
        """Create a new run."""
        run_id = uuid4()
        row = await self._db.fetch_one(
            """
            INSERT INTO runs (run_id, thread_id, assistant_id, input, kwargs, metadata_, multitask_strategy)
            VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, $6::jsonb, $7)
            RETURNING *
            """,
            run_id,
            thread_id,
            assistant_id,
            orjson.dumps(input).decode() if input is not None else None,
            orjson.dumps(kwargs or {}).decode(),
            orjson.dumps(metadata or {}).decode(),
            multitask_strategy,
        )
        return self._normalize(row)

    async def get(self, run_id: UUID) -> dict:
        """Get a run by ID."""
        row = await self._db.fetch_one(
            "SELECT * FROM runs WHERE run_id = $1", run_id
        )
        if row is None:
            raise NotFoundError("run", str(run_id))
        return self._normalize(row)

    async def update_status(self, run_id: UUID, status: str, error: str | None = None, result: Any | None = None) -> None:
        """Update run status."""
        if result is not None:
            await self._db.execute(
                "UPDATE runs SET status = $1, error = $2, result = $3::jsonb, updated_at = NOW() WHERE run_id = $4",
                status, error, orjson.dumps(result).decode(), run_id,
            )
        else:
            await self._db.execute(
                "UPDATE runs SET status = $1, error = $2, updated_at = NOW() WHERE run_id = $3",
                status, error, run_id,
            )

    async def delete(self, run_id: UUID) -> None:
        """Delete a run."""
        result = await self._db.execute(
            "DELETE FROM runs WHERE run_id = $1", run_id
        )
        if result == "DELETE 0":
            raise NotFoundError("run", str(run_id))

    async def search(
        self,
        *,
        thread_id: UUID | None = None,
        assistant_id: UUID | None = None,
        status: str | None = None,
        metadata: dict[str, Any] | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> list[dict]:
        """Search runs."""
        conditions = []
        args = []
        idx = 1

        if thread_id is not None:
            conditions.append(f"thread_id = ${idx}")
            args.append(thread_id)
            idx += 1

        if assistant_id is not None:
            conditions.append(f"assistant_id = ${idx}")
            args.append(assistant_id)
            idx += 1

        if status is not None:
            conditions.append(f"status = ${idx}")
            args.append(status)
            idx += 1

        if metadata:
            conditions.append(f"metadata_ @> ${idx}::jsonb")
            args.append(orjson.dumps(metadata).decode())
            idx += 1

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        args.extend([limit, offset])

        rows = await self._db.fetch_all(
            f"SELECT * FROM runs {where} ORDER BY created_at DESC LIMIT ${idx} OFFSET ${idx + 1}",
            *args,
        )
        return [self._normalize(r) for r in rows]

    async def list_by_thread(self, thread_id: UUID, limit: int = 10, offset: int = 0) -> list[dict]:
        """List runs for a specific thread."""
        return await self.search(thread_id=thread_id, limit=limit, offset=offset)

    @staticmethod
    def _normalize(row: dict | None) -> dict:
        if row is None:
            return {}
        result = dict(row)
        if "metadata_" in result:
            result["metadata"] = result.pop("metadata_")
        return result
