"""Task publisher -- adds background run tasks to Redis Streams."""

from __future__ import annotations

from typing import Any

import orjson


TASK_STREAM = "langrove:tasks"


class TaskPublisher:
    """Publishes background run tasks to Redis Streams via XADD."""

    def __init__(self, redis: Any):
        self._redis = redis

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
    ) -> str:
        """Publish a task to the Redis Stream.

        Returns the stream message ID.
        """
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
        }

        message_id = await self._redis.xadd(
            TASK_STREAM,
            {"payload": orjson.dumps(payload).decode()},
        )
        return message_id
