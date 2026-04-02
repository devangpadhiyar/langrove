"""Business logic for cron jobs."""

from __future__ import annotations

from uuid import UUID

from langrove.db.cron_repo import CronRepository
from langrove.models.crons import Cron, CronCreate, CronSearchRequest, CronUpdate


class CronService:
    """Manages cron job lifecycle."""

    def __init__(self, repo: CronRepository):
        self._repo = repo

    async def create(self, req: CronCreate, thread_id: UUID | None = None) -> Cron:
        """Create a new cron job."""
        row = await self._repo.create(
            assistant_id=UUID(req.assistant_id),
            schedule=req.schedule,
            thread_id=thread_id or req.thread_id,
            payload=req.payload,
            metadata=req.metadata,
        )
        return self._to_model(row)

    async def update(self, cron_id: UUID, req: CronUpdate) -> Cron:
        """Update a cron job."""
        fields = req.model_dump(exclude_none=True)
        row = await self._repo.update(cron_id, **fields)
        return self._to_model(row)

    async def delete(self, cron_id: UUID) -> None:
        """Delete a cron job."""
        await self._repo.delete(cron_id)

    async def search(self, req: CronSearchRequest) -> list[Cron]:
        """Search cron jobs."""
        rows = await self._repo.search(
            assistant_id=req.assistant_id,
            thread_id=req.thread_id,
            limit=req.limit,
            offset=req.offset,
        )
        return [self._to_model(r) for r in rows]

    @staticmethod
    def _to_model(row: dict) -> Cron:
        return Cron(
            cron_id=row["cron_id"],
            assistant_id=row["assistant_id"],
            thread_id=row.get("thread_id"),
            schedule=row["schedule"],
            payload=row.get("payload", {}),
            metadata=row.get("metadata", {}),
            enabled=row.get("enabled", True),
            next_run_date=row.get("next_run_date"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
