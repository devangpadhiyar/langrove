"""Task publisher -- enqueues background run tasks via Dramatiq."""

from __future__ import annotations

import asyncio
from typing import Any


class TaskPublisher:
    """Publishes background run tasks via the Dramatiq broker.

    Calls ``handle_run.send_with_options(kwargs=payload)`` in a thread pool
    (Dramatiq's broker operations are synchronous) so the async API event loop
    is not blocked.

    No broker instance is passed — Dramatiq uses the global broker registered
    by ``queue.broker.setup_broker()``, which is called at API server startup.
    """

    async def publish(
        self,
        *,
        run_id: str,
        thread_id: str | None,
        assistant_id: str,
        graph_id: str,
        input: Any | None = None,
        command: dict[str, Any] | None = None,
        config: dict[str, Any] | None = None,
        stream_mode: str | list[str] = "values",
        stream_subgraphs: bool = False,
        interrupt_before: list[str] | None = None,
        interrupt_after: list[str] | None = None,
        checkpoint_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        auth_user: dict[str, Any] | None = None,
    ) -> str:
        """Enqueue a background run task. Returns the run_id."""
        # Lazy import ensures setup_broker() has already been called.
        from langrove.queue.tasks import handle_run

        payload = {
            "run_id": run_id,
            "thread_id": thread_id,
            "assistant_id": assistant_id,
            "graph_id": graph_id,
            "input": input,
            "command": command,
            "config": config,
            "stream_mode": stream_mode,
            "stream_subgraphs": stream_subgraphs,
            "interrupt_before": interrupt_before,
            "interrupt_after": interrupt_after,
            "checkpoint_id": checkpoint_id,
            "metadata": metadata or {},
            "auth_user": auth_user,
        }
        # send_with_options is synchronous (Redis RPUSH); run in thread pool.
        await asyncio.to_thread(handle_run.send_with_options, kwargs=payload)
        return run_id
