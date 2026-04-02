"""Task consumer -- reads from Redis Streams with consumer groups and late-ack."""

from __future__ import annotations

import asyncio
import logging
import traceback
from typing import Any

import orjson

logger = logging.getLogger(__name__)

from langrove.queue.publisher import TASK_STREAM

CONSUMER_GROUP = "langrove:workers"
DEAD_LETTER_STREAM = "langrove:tasks:dead"


class TaskConsumer:
    """Consumes background run tasks from Redis Streams.

    Uses consumer groups for at-least-once delivery:
    - XREADGROUP to read tasks (enters Pending Entries List)
    - XACK only after successful execution (late acknowledgment)
    - On crash: unacked tasks stay in PEL for recovery
    """

    def __init__(self, redis: Any, worker_id: str):
        self._redis = redis
        self._worker_id = worker_id

    async def setup(self) -> None:
        """Ensure the consumer group exists."""
        try:
            await self._redis.xgroup_create(
                TASK_STREAM, CONSUMER_GROUP, id="0", mkstream=True
            )
        except Exception:
            # Group already exists
            pass

    async def consume_one(self, block_ms: int = 5000) -> tuple[str, dict] | None:
        """Consume a single task from the stream.

        First checks for previously unacked messages (crash recovery),
        then reads new messages.

        Returns (message_id, payload) or None if no tasks available.
        """
        # 1. Check for pending (previously unacked) messages
        pending = await self._redis.xreadgroup(
            CONSUMER_GROUP, self._worker_id,
            {TASK_STREAM: "0"},
            count=1,
        )
        if pending and pending[0][1]:
            msg_id, fields = pending[0][1][0]
            return msg_id, orjson.loads(fields["payload"])

        # 2. Read new messages (blocking)
        result = await self._redis.xreadgroup(
            CONSUMER_GROUP, self._worker_id,
            {TASK_STREAM: ">"},
            count=1,
            block=block_ms,
        )
        if result and result[0][1]:
            msg_id, fields = result[0][1][0]
            return msg_id, orjson.loads(fields["payload"])

        return None

    async def acknowledge(self, message_id: str) -> None:
        """Acknowledge a successfully processed task (late-ack)."""
        await self._redis.xack(TASK_STREAM, CONSUMER_GROUP, message_id)

    async def run_loop(self, handler) -> None:
        """Main consumer loop. Calls handler(payload) for each task.

        handler should be an async callable that processes the task.
        """
        await self.setup()

        while True:
            try:
                task = await self.consume_one()
                if task is None:
                    continue

                msg_id, payload = task

                try:
                    await handler(payload)
                    await self.acknowledge(msg_id)
                except Exception as e:
                    # Don't ack -- task stays in PEL for recovery
                    logger.error(
                        "Task %s failed: %s\n%s",
                        payload.get("run_id"),
                        e,
                        traceback.format_exc(),
                    )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Consumer error: %s\n%s", e, traceback.format_exc())
                await asyncio.sleep(1)
