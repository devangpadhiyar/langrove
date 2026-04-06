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
        await self._repo.get(thread_id)

        graph = self._get_graph_with_checkpointer()
        if graph is None:
            return ThreadState()

        config = {"configurable": {"thread_id": str(thread_id)}}
        if checkpoint_id:
            config["configurable"]["checkpoint_id"] = checkpoint_id

        state_snapshot = await graph.aget_state(config)
        return self._snapshot_to_thread_state(state_snapshot)

    async def update_state(self, thread_id: UUID, req: ThreadStateUpdate) -> ThreadState:
        """Update thread state via the checkpointer (creates new checkpoint)."""
        await self._repo.get(thread_id)

        graph = self._get_graph_with_checkpointer()
        if graph is None:
            return ThreadState(values=req.values)

        config = {"configurable": {"thread_id": str(thread_id)}}
        if req.checkpoint_id:
            config["configurable"]["checkpoint_id"] = req.checkpoint_id

        await graph.aupdate_state(
            config,
            req.values,
            as_node=req.as_node,
        )

        return await self.get_state(thread_id)

    async def get_history(self, thread_id: UUID, req: ThreadHistoryRequest) -> list[ThreadState]:
        """Get thread state history from checkpoints."""
        await self._repo.get(thread_id)

        graph = self._get_graph_with_checkpointer()
        if graph is None:
            return []

        config = {"configurable": {"thread_id": str(thread_id)}}
        if req.checkpoint_id:
            config["configurable"]["checkpoint_id"] = req.checkpoint_id

        before_config = {"configurable": {"checkpoint_id": req.before}} if req.before else None

        states = []
        async for state_snapshot in graph.aget_state_history(
            config, limit=req.limit, before=before_config
        ):
            states.append(self._snapshot_to_thread_state(state_snapshot))

        return states

    async def _get_checkpoint_state(self, thread_id: UUID) -> dict | None:
        """Get the latest checkpoint values for a thread."""
        graph = self._get_graph_with_checkpointer()
        if graph is None:
            return None

        config = {"configurable": {"thread_id": str(thread_id)}}
        state_snapshot = await graph.aget_state(config)
        if state_snapshot and state_snapshot.values:
            return {
                "values": state_snapshot.values,
                "interrupts": getattr(state_snapshot, "interrupts", None),
            }
        return None

    def _get_graph_with_checkpointer(self) -> Any:
        """Get a graph copy with checkpointer injected. Returns None if unavailable."""
        if not self._checkpointer:
            return None
        graphs = self._registry.list_graphs()
        if not graphs:
            return None
        return self._registry.get_graph_for_request(graphs[0].graph_id, self._checkpointer)

    @staticmethod
    def _snapshot_to_thread_state(snapshot: Any) -> ThreadState:
        """Convert a LangGraph StateSnapshot to our ThreadState model."""
        if not snapshot or not snapshot.values:
            return ThreadState()
        return ThreadState(
            values=snapshot.values or {},
            next=list(snapshot.next) if snapshot.next else [],
            checkpoint={
                "checkpoint_id": snapshot.config.get("configurable", {}).get("checkpoint_id", "")
            },
            metadata=snapshot.metadata or {},
            tasks=[
                {
                    "id": getattr(t, "id", ""),
                    "name": getattr(t, "name", ""),
                    "interrupts": [
                        {
                            "value": getattr(i, "value", i),
                            "id": getattr(i, "id", None),
                            "resumable": getattr(i, "resumable", True),
                            "ns": getattr(i, "ns", None),
                            "when": getattr(i, "when", "during"),
                        }
                        for i in getattr(t, "interrupts", [])
                    ],
                }
                for t in (snapshot.tasks or [])
            ],
        )

    @staticmethod
    def _to_thread(row: dict) -> Thread:
        return Thread(
            thread_id=row["thread_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            metadata=row.get("metadata", {}),
            status=row.get("status", "idle"),
        )
