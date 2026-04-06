"""Repository for cron CRUD operations."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import orjson

from langrove.db.pool import DatabasePool
from langrove.exceptions import NotFoundError


class CronRepository:
    """Data access for the crons table."""

    def __init__(self, db: DatabasePool):
        self._db = db

    async def create(
        self,
        *,
        assistant_id: UUID,
        schedule: str,
        thread_id: UUID | None = None,
        payload: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict:
        """Create a new cron job."""
        row = await self._db.fetch_one(
            """
            INSERT INTO crons (cron_id, assistant_id, thread_id, schedule, payload, metadata_)
            VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb)
            RETURNING *
            """,
            uuid4(),
            assistant_id,
            thread_id,
            schedule,
            orjson.dumps(payload or {}).decode(),
            orjson.dumps(metadata or {}).decode(),
        )
        return self._normalize(row)

    async def get(self, cron_id: UUID) -> dict:
        """Get a cron by ID."""
        row = await self._db.fetch_one("SELECT * FROM crons WHERE cron_id = $1", cron_id)
        if row is None:
            raise NotFoundError("cron", str(cron_id))
        return self._normalize(row)

    async def update(self, cron_id: UUID, **fields) -> dict:
        """Update a cron."""
        sets = []
        args = []
        idx = 1

        for key in ("schedule", "enabled"):
            if key in fields and fields[key] is not None:
                sets.append(f"{key} = ${idx}")
                args.append(fields[key])
                idx += 1

        for key in ("payload", "metadata"):
            if key in fields and fields[key] is not None:
                db_key = "metadata_" if key == "metadata" else key
                sets.append(f"{db_key} = ${idx}::jsonb")
                args.append(orjson.dumps(fields[key]).decode())
                idx += 1

        if not sets:
            return await self.get(cron_id)

        sets.append("updated_at = NOW()")
        args.append(cron_id)

        row = await self._db.fetch_one(
            f"UPDATE crons SET {', '.join(sets)} WHERE cron_id = ${idx} RETURNING *",
            *args,
        )
        if row is None:
            raise NotFoundError("cron", str(cron_id))
        return self._normalize(row)

    async def delete(self, cron_id: UUID) -> None:
        """Delete a cron."""
        result = await self._db.execute("DELETE FROM crons WHERE cron_id = $1", cron_id)
        if result == "DELETE 0":
            raise NotFoundError("cron", str(cron_id))

    async def search(
        self,
        *,
        assistant_id: UUID | None = None,
        thread_id: UUID | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> list[dict]:
        """Search crons."""
        conditions = []
        args = []
        idx = 1

        if assistant_id is not None:
            conditions.append(f"assistant_id = ${idx}")
            args.append(assistant_id)
            idx += 1

        if thread_id is not None:
            conditions.append(f"thread_id = ${idx}")
            args.append(thread_id)
            idx += 1

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        args.extend([limit, offset])

        rows = await self._db.fetch_all(
            f"SELECT * FROM crons {where} ORDER BY created_at DESC LIMIT ${idx} OFFSET ${idx + 1}",
            *args,
        )
        return [self._normalize(r) for r in rows]

    @staticmethod
    def _normalize(row: dict | None) -> dict:
        if row is None:
            return {}
        result = dict(row)
        if "metadata_" in result:
            result["metadata"] = result.pop("metadata_")
        return result
