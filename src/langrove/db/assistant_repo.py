"""Repository for assistant CRUD operations."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from langrove.db.pool import DatabasePool
from langrove.exceptions import NotFoundError


class AssistantRepository:
    """Data access for the assistants table."""

    def __init__(self, db: DatabasePool):
        self._db = db

    async def create(
        self,
        graph_id: str,
        *,
        assistant_id: UUID | None = None,
        name: str = "",
        description: str | None = None,
        config: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict:
        """Insert a new assistant. Returns the created row as dict."""
        aid = assistant_id or uuid4()
        import orjson

        row = await self._db.fetch_one(
            """
            INSERT INTO langrove_assistants (assistant_id, graph_id, name, description, config, metadata_)
            VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb)
            RETURNING *
            """,
            aid,
            graph_id,
            name,
            description,
            orjson.dumps(config or {}).decode(),
            orjson.dumps(metadata or {}).decode(),
        )
        return self._normalize(row)

    async def get(self, assistant_id: UUID) -> dict:
        """Get an assistant by ID. Raises NotFoundError if not found."""
        row = await self._db.fetch_one(
            "SELECT * FROM langrove_assistants WHERE assistant_id = $1",
            assistant_id,
        )
        if row is None:
            raise NotFoundError("assistant", str(assistant_id))
        return self._normalize(row)

    async def update(self, assistant_id: UUID, **fields) -> dict:
        """Update an assistant. Only non-None fields are updated."""
        import orjson

        # Build SET clause dynamically
        sets = []
        args = []
        idx = 1

        for key in ("name", "description", "graph_id"):
            if key in fields and fields[key] is not None:
                sets.append(f"{key} = ${idx}")
                args.append(fields[key])
                idx += 1

        for key in ("config", "metadata"):
            if key in fields and fields[key] is not None:
                db_key = "metadata_" if key == "metadata" else key
                sets.append(f"{db_key} = ${idx}::jsonb")
                args.append(orjson.dumps(fields[key]).decode())
                idx += 1

        if not sets:
            return await self.get(assistant_id)

        sets.append("version = version + 1")
        sets.append("updated_at = NOW()")
        args.append(assistant_id)

        row = await self._db.fetch_one(
            f"UPDATE langrove_assistants SET {', '.join(sets)} WHERE assistant_id = ${idx} RETURNING *",
            *args,
        )
        if row is None:
            raise NotFoundError("assistant", str(assistant_id))

        # Save version history
        await self._save_version(row)

        return self._normalize(row)

    async def delete(self, assistant_id: UUID) -> None:
        """Delete an assistant by ID."""
        result = await self._db.execute(
            "DELETE FROM langrove_assistants WHERE assistant_id = $1",
            assistant_id,
        )
        if result == "DELETE 0":
            raise NotFoundError("assistant", str(assistant_id))

    async def search(
        self,
        *,
        name: str | None = None,
        graph_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> list[dict]:
        """Search assistants with optional filters."""
        import orjson

        conditions = []
        args = []
        idx = 1

        if name is not None:
            conditions.append(f"name ILIKE ${idx}")
            args.append(f"%{name}%")
            idx += 1

        if graph_id is not None:
            conditions.append(f"graph_id = ${idx}")
            args.append(graph_id)
            idx += 1

        if metadata:
            conditions.append(f"metadata_ @> ${idx}::jsonb")
            args.append(orjson.dumps(metadata).decode())
            idx += 1

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        args.extend([limit, offset])

        rows = await self._db.fetch_all(
            f"SELECT * FROM langrove_assistants {where} ORDER BY created_at DESC LIMIT ${idx} OFFSET ${idx + 1}",
            *args,
        )
        return [self._normalize(r) for r in rows]

    async def _save_version(self, row: dict) -> None:
        """Save a version snapshot."""
        import orjson

        await self._db.execute(
            """
            INSERT INTO langrove_assistant_versions (assistant_id, version, graph_id, config, metadata_)
            VALUES ($1, $2, $3, $4::jsonb, $5::jsonb)
            ON CONFLICT (assistant_id, version) DO NOTHING
            """,
            row["assistant_id"],
            row["version"],
            row["graph_id"],
            orjson.dumps(row.get("config", {})).decode()
            if isinstance(row.get("config"), dict)
            else row.get("config", "{}"),
            orjson.dumps(row.get("metadata", {})).decode()
            if isinstance(row.get("metadata"), dict)
            else row.get("metadata_", "{}"),
        )

    @staticmethod
    def _normalize(row: dict | None) -> dict:
        """Normalize DB row: rename metadata_ -> metadata."""
        if row is None:
            return {}
        result = dict(row)
        if "metadata_" in result:
            result["metadata"] = result.pop("metadata_")
        return result
