"""Business logic for threads."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from langrove.db.thread_repo import ThreadRepository
from langrove.graph.registry import GraphRegistry
from langrove.models.threads import (
    Thread,
    ThreadCreate,
    ThreadHistoryRequest,
    ThreadPatch,
    ThreadSearchRequest,
    ThreadState,
    ThreadStateUpdate,
)


class ThreadService:
    """Manages thread lifecycle and state access via checkpointer."""

    def __init__(self, repo: ThreadRepository, checkpointer: Any, registry: GraphRegistry):
        self._repo = repo
        self._checkpointer = checkpointer
        self._registry = registry

    async def create(self, req: ThreadCreate) -> Thread:
        """Create a new thread."""
        row = await self._repo.create(
            thread_id=req.thread_id,
            metadata=req.metadata,
            if_exists=req.if_exists,
        )
        return self._to_thread(row)

    async def get(self, thread_id: UUID) -> Thread:
        """Get a thread with current state derived from checkpointer."""
        row = await self._repo.get(thread_id)
        thread = self._to_thread(row)

        # Enrich with state from checkpointer
        if self._checkpointer:
            state = await self._get_checkpoint_state(thread_id)
            if state:
                thread.values = state.get("values")
                thread.interrupts = state.get("interrupts")

        return thread

    async def update(self, thread_id: UUID, req: ThreadPatch) -> Thread:
        """Update thread metadata."""
        row = await self._repo.update(thread_id, metadata=req.metadata)
        return self._to_thread(row)

    async def delete(self, thread_id: UUID) -> None:
        """Delete a thread."""
        await self._repo.delete(thread_id)

    async def search(self, req: ThreadSearchRequest) -> list[Thread]:
        """Search threads."""
        rows = await self._repo.search(
            metadata=req.metadata,
            status=req.status,
            limit=req.limit,
            offset=req.offset,
        )
        return [self._to_thread(r) for r in rows]

    async def copy(self, thread_id: UUID) -> Thread:
        """Copy a thread."""
        row = await self._repo.copy(thread_id)
        return self._to_thread(row)

    async def get_state(self, thread_id: UUID, checkpoint_id: str | None = None) -> ThreadState:
        """Get current thread state from the checkpointer."""
        # Ensure thread exists
        await self._repo.get(thread_id)

        if not self._checkpointer:
            return ThreadState()

        config = {"configurable": {"thread_id": str(thread_id)}}
        if checkpoint_id:
            config["configurable"]["checkpoint_id"] = checkpoint_id

        try:
            state_snapshot = await self._checkpointer.aget_tuple(config)
            if state_snapshot is None:
                return ThreadState()

            return ThreadState(
                values=state_snapshot.values or {},
                next=list(state_snapshot.next) if state_snapshot.next else [],
                checkpoint={"checkpoint_id": state_snapshot.config.get("configurable", {}).get("checkpoint_id", "")},
                metadata=state_snapshot.metadata or {},
                tasks=[
                    {
                        "id": getattr(t, "id", ""),
                        "name": getattr(t, "name", ""),
                    }
                    for t in (state_snapshot.tasks or [])
                ],
            )
        except Exception:
            return ThreadState()

    async def update_state(self, thread_id: UUID, req: ThreadStateUpdate) -> ThreadState:
        """Update thread state via the checkpointer (creates new checkpoint)."""
        await self._repo.get(thread_id)

        if not self._checkpointer:
            return ThreadState(values=req.values)

        # Find the graph for this thread
        graph = self._find_graph_for_thread(thread_id)
        if graph is None:
            return ThreadState(values=req.values)

        config = {"configurable": {"thread_id": str(thread_id)}}
        if req.checkpoint_id:
            config["configurable"]["checkpoint_id"] = req.checkpoint_id

        try:
            await graph.aupdate_state(
                config,
                req.values,
                as_node=req.as_node,
            )
        except Exception:
            pass

        return await self.get_state(thread_id)

    async def get_history(self, thread_id: UUID, req: ThreadHistoryRequest) -> list[ThreadState]:
        """Get thread state history from checkpoints."""
        await self._repo.get(thread_id)

        if not self._checkpointer:
            return []

        config = {"configurable": {"thread_id": str(thread_id)}}
        if req.checkpoint_id:
            config["configurable"]["checkpoint_id"] = req.checkpoint_id

        states = []
        try:
            async for state_snapshot in self._checkpointer.alist(config, limit=req.limit, before=req.before):
                states.append(ThreadState(
                    values=state_snapshot.values or {},
                    next=list(state_snapshot.next) if state_snapshot.next else [],
                    checkpoint={"checkpoint_id": state_snapshot.config.get("configurable", {}).get("checkpoint_id", "")},
                    metadata=state_snapshot.metadata or {},
                ))
        except Exception:
            pass

        return states

    async def _get_checkpoint_state(self, thread_id: UUID) -> dict | None:
        """Get the latest checkpoint values for a thread."""
        config = {"configurable": {"thread_id": str(thread_id)}}
        try:
            state = await self._checkpointer.aget_tuple(config)
            if state:
                return {"values": state.values, "interrupts": getattr(state, "interrupts", None)}
        except Exception:
            pass
        return None

    def _find_graph_for_thread(self, thread_id: UUID) -> Any:
        """Find the appropriate graph for a thread. Returns first available graph."""
        graphs = self._registry.list_graphs()
        if graphs:
            return self._registry.get_graph_for_request(
                graphs[0].graph_id, self._checkpointer
            )
        return None

    @staticmethod
    def _to_thread(row: dict) -> Thread:
        return Thread(
            thread_id=row["thread_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            metadata=row.get("metadata", {}),
            status=row.get("status", "idle"),
        )
