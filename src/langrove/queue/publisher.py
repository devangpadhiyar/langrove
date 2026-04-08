"""Task publisher -- enqueues background run tasks via Taskiq."""

from __future__ import annotations

from typing import Any

from taskiq import TaskiqMessage


class TaskPublisher:
    """Publishes background run tasks to the Taskiq broker (Redis Streams).

    Wraps a Taskiq AsyncBroker. Each call to publish() kicks a
    'handle_run' job that the Taskiq worker will pick up and execute
    with at-least-once delivery via Redis Streams XREADGROUP/XACK.
    """

    def __init__(self, broker: Any):
        self._broker = broker

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
        """Enqueue a background run task.

        Returns the task ID (run_id used for idempotency).
        """
        msg = TaskiqMessage(
            task_id=run_id,  # Use run_id as task_id for traceability
            task_name="handle_run",
            labels={},
            args=[],
            kwargs={
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
            },
        )
        await self._broker.kick(msg)
        return run_id
