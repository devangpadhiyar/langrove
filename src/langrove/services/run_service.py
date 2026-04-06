"""Business logic for runs -- foreground execution and background dispatch."""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from uuid import UUID

from langrove.db.assistant_repo import AssistantRepository
from langrove.db.run_repo import RunRepository
from langrove.db.thread_repo import ThreadRepository
from langrove.models.common import StreamPart
from langrove.models.runs import Run, RunCreate, RunSearchRequest, RunWaitResponse
from langrove.queue.publisher import TaskPublisher
from langrove.streaming.executor import RunExecutor


class RunService:
    """Orchestrates run execution -- foreground streaming, blocking wait, and background dispatch."""

    def __init__(
        self,
        run_repo: RunRepository,
        thread_repo: ThreadRepository,
        assistant_repo: AssistantRepository,
        executor: RunExecutor,
        publisher: TaskPublisher | None = None,
    ):
        self._runs = run_repo
        self._threads = thread_repo
        self._assistants = assistant_repo
        self._executor = executor
        self._publisher = publisher

    async def stream_run(
        self,
        req: RunCreate,
        thread_id: UUID | None = None,
    ) -> tuple[str, AsyncIterator[StreamPart]]:
        """Execute a foreground streaming run.

        Returns (run_id, stream_iterator).
        The caller is responsible for formatting as SSE.
        """
        assistant = await self._resolve_assistant(req.assistant_id)
        graph_id = assistant["graph_id"]

        # Create or use thread
        actual_thread_id = thread_id
        ephemeral = False
        if actual_thread_id is None:
            thread = await self._threads.create()
            actual_thread_id = thread["thread_id"]
            ephemeral = req.on_completion == "delete"

        # Create run record
        run = await self._runs.create(
            assistant_id=assistant["assistant_id"],
            thread_id=actual_thread_id,
            input=req.input,
            metadata=req.metadata,
            multitask_strategy=req.multitask_strategy,
        )
        run_id = str(run["run_id"])

        # Set thread to busy
        await self._threads.set_status(actual_thread_id, "busy")

        async def generate():
            try:
                await self._runs.update_status(run["run_id"], "running")

                async for part in self._executor.execute_stream(
                    graph_id,
                    input=req.input,
                    command=req.command,
                    config=req.config,
                    thread_id=str(actual_thread_id),
                    stream_mode=req.stream_mode or "values",
                    stream_subgraphs=req.stream_subgraphs,
                    interrupt_before=req.interrupt_before,
                    interrupt_after=req.interrupt_after,
                    checkpoint_id=req.checkpoint_id,
                ):
                    yield part

                await self._runs.update_status(run["run_id"], "success")
                await self._threads.set_status(actual_thread_id, "idle")

            except Exception as e:
                await self._runs.update_status(run["run_id"], "error", error=str(e))
                await self._threads.set_status(actual_thread_id, "error")
                yield StreamPart("error", {"error": str(e), "message": type(e).__name__})

            finally:
                if ephemeral:
                    with contextlib.suppress(Exception):
                        await self._threads.delete(actual_thread_id)

        return run_id, generate()

    async def wait_run(
        self,
        req: RunCreate,
        thread_id: UUID | None = None,
    ) -> RunWaitResponse:
        """Execute a blocking run and return the final state."""
        assistant = await self._resolve_assistant(req.assistant_id)
        graph_id = assistant["graph_id"]

        actual_thread_id = thread_id
        ephemeral = False
        if actual_thread_id is None:
            thread = await self._threads.create()
            actual_thread_id = thread["thread_id"]
            ephemeral = req.on_completion == "delete"

        run = await self._runs.create(
            assistant_id=assistant["assistant_id"],
            thread_id=actual_thread_id,
            input=req.input,
            metadata=req.metadata,
        )

        await self._threads.set_status(actual_thread_id, "busy")
        await self._runs.update_status(run["run_id"], "running")

        try:
            result = await self._executor.execute_wait(
                graph_id,
                input=req.input,
                command=req.command,
                config=req.config,
                thread_id=str(actual_thread_id),
                interrupt_before=req.interrupt_before,
                interrupt_after=req.interrupt_after,
                checkpoint_id=req.checkpoint_id,
            )

            await self._runs.update_status(run["run_id"], "success", result=result)
            await self._threads.set_status(actual_thread_id, "idle")

            messages = result.get("messages", [])
            return RunWaitResponse(values=result, messages=messages)

        except Exception as e:
            await self._runs.update_status(run["run_id"], "error", error=str(e))
            await self._threads.set_status(actual_thread_id, "error")
            raise

        finally:
            if ephemeral:
                with contextlib.suppress(Exception):
                    await self._threads.delete(actual_thread_id)

    async def background_run(
        self,
        req: RunCreate,
        thread_id: UUID | None = None,
    ) -> Run:
        """Create a background run and dispatch it to the Redis Streams worker."""
        assistant = await self._resolve_assistant(req.assistant_id)
        graph_id = assistant["graph_id"]

        # Create or use thread
        actual_thread_id = thread_id
        if actual_thread_id is None:
            thread = await self._threads.create()
            actual_thread_id = thread["thread_id"]

        run = await self._runs.create(
            assistant_id=assistant["assistant_id"],
            thread_id=actual_thread_id,
            input=req.input,
            metadata=req.metadata,
            multitask_strategy=req.multitask_strategy,
        )
        run_id = str(run["run_id"])

        # Dispatch to Redis Streams for the worker to pick up
        if self._publisher:
            await self._publisher.publish(
                run_id=run_id,
                thread_id=str(actual_thread_id),
                assistant_id=str(assistant["assistant_id"]),
                graph_id=graph_id,
                input=req.input,
                command=req.command,
                config=req.config,
                stream_mode=req.stream_mode or "values",
                stream_subgraphs=req.stream_subgraphs,
                interrupt_before=req.interrupt_before,
                interrupt_after=req.interrupt_after,
                checkpoint_id=req.checkpoint_id,
                metadata=req.metadata,
            )

        return Run(**self._to_model(run))

    async def get_run(self, run_id: UUID) -> Run:
        """Get a run by ID."""
        row = await self._runs.get(run_id)
        return Run(**self._to_model(row))

    async def cancel_run(self, run_id: UUID) -> None:
        """Cancel a run."""
        await self._runs.update_status(run_id, "interrupted")

    async def delete_run(self, run_id: UUID) -> None:
        """Delete a run."""
        await self._runs.delete(run_id)

    async def search_runs(self, req: RunSearchRequest) -> list[Run]:
        """Search runs."""
        rows = await self._runs.search(
            thread_id=req.thread_id,
            assistant_id=req.assistant_id,
            status=req.status,
            metadata=req.metadata,
            limit=req.limit,
            offset=req.offset,
        )
        return [Run(**self._to_model(r)) for r in rows]

    async def list_thread_runs(
        self, thread_id: UUID, limit: int = 10, offset: int = 0
    ) -> list[Run]:
        """List runs for a thread."""
        rows = await self._runs.list_by_thread(thread_id, limit=limit, offset=offset)
        return [Run(**self._to_model(r)) for r in rows]

    async def _resolve_assistant(self, assistant_id: str | None) -> dict:
        """Resolve assistant by ID or name. Falls back to first available."""
        if assistant_id:
            try:
                return await self._assistants.get(UUID(assistant_id))
            except (ValueError, Exception):
                # Try by graph_id name
                results = await self._assistants.search(graph_id=assistant_id, limit=1)
                if results:
                    return results[0]

        # Fall back to first assistant
        results = await self._assistants.search(limit=1)
        if results:
            return results[0]

        from langrove.exceptions import NotFoundError

        raise NotFoundError("assistant", assistant_id or "default")

    @staticmethod
    def _to_model(row: dict) -> dict:
        return {
            "run_id": row["run_id"],
            "thread_id": row.get("thread_id"),
            "assistant_id": row.get("assistant_id"),
            "status": row.get("status", "pending"),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "metadata": row.get("metadata", {}),
            "kwargs": row.get("kwargs", {}),
            "multitask_strategy": row.get("multitask_strategy", "reject"),
        }
