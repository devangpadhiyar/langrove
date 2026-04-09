"""Task publisher -- enqueues background run tasks via Celery."""

from __future__ import annotations

import asyncio
from typing import Any


class TaskPublisher:
    """Publishes background run tasks to the Celery queue.

    Uses the run_id as the Celery task_id for easy cancellation lookup.
    apply_async is synchronous (Redis LPUSH); asyncio.to_thread keeps the
    API event loop non-blocking.
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
        from langrove.queue.tasks import handle_run
        from langrove.settings import Settings

        settings = Settings()
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
        # apply_async is synchronous (Redis LPUSH); run in thread pool
        await asyncio.to_thread(
            handle_run.apply_async,
            kwargs=payload,
            task_id=run_id,  # task_id == run_id for easy cancellation
            queue=settings.queue_name,
        )
        return run_id
