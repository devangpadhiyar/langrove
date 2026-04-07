"""Task consumer -- reads from Redis Streams with consumer groups and late-ack."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import traceback
from typing import Any

import orjson

from langrove.queue.publisher import TASK_STREAM

logger = logging.getLogger(__name__)

CONSUMER_GROUP = "langrove:workers"
DEAD_LETTER_STREAM = "langrove:tasks:dead"


class TaskConsumer:
    """Consumes background run tasks from Redis Streams.

    Uses consumer groups for at-least-once delivery:
    - XREADGROUP to read tasks (enters Pending Entries List)
    - XACK only after successful execution (late acknowledgment)
    - On crash: unacked tasks stay in PEL for recovery

    Supports concurrent task execution via a semaphore. Set concurrency > 1
    to allow multiple tasks to run in parallel within one worker process.
    """

    def __init__(self, redis: Any, worker_id: str, *, concurrency: int = 1):
        self._redis = redis
        self._worker_id = worker_id
        self._concurrency = concurrency
        self._semaphore: asyncio.Semaphore | None = None
        self._tasks: set[asyncio.Task] = set()
        self._in_flight_ids: set[str] = set()  # message IDs currently being processed

    @property
    def in_flight_tasks(self) -> set[asyncio.Task]:
        """Currently executing tasks (for graceful shutdown draining)."""
        return set(self._tasks)

    async def setup(self) -> None:
        """Ensure the consumer group exists."""
        with contextlib.suppress(Exception):
            await self._redis.xgroup_create(TASK_STREAM, CONSUMER_GROUP, id="0", mkstream=True)

    async def consume_one(self, block_ms: int = 5000) -> tuple[str, dict] | None:
        """Consume a single task from the stream.

        First checks for previously unacked messages (crash recovery),
        then reads new messages.

        Skips any message already being processed by this worker (deduplication
        across concurrent slots -- prevents multiple slots from claiming the
        same pending message simultaneously).

        Returns (message_id, payload) or None if no tasks available.
        """
        # 1. Check for pending (previously unacked) messages
        pending = await self._redis.xreadgroup(
            CONSUMER_GROUP,
            self._worker_id,
            {TASK_STREAM: "0"},
            count=1,
        )
        if pending and pending[0][1]:
            msg_id, fields = pending[0][1][0]
            if msg_id not in self._in_flight_ids:
                return msg_id, orjson.loads(fields["payload"])
            # This pending message is already being handled by another slot;
            # fall through to read a new message instead.

        # 2. Read new messages (blocking)
        result = await self._redis.xreadgroup(
            CONSUMER_GROUP,
            self._worker_id,
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
        Tasks run concurrently up to self._concurrency limit.
        """
        await self.setup()
        self._semaphore = asyncio.Semaphore(self._concurrency)

        while True:
            try:
                await self._semaphore.acquire()
                task = await self.consume_one()
                if task is None:
                    self._semaphore.release()
                    continue

                msg_id, payload = task
                self._in_flight_ids.add(msg_id)
                t = asyncio.create_task(self._handle_one(handler, msg_id, payload))
                self._tasks.add(t)
                t.add_done_callback(self._tasks.discard)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self._semaphore.release()
                logger.error("Consumer error: %s\n%s", e, traceback.format_exc())
                await asyncio.sleep(1)

    async def _handle_one(self, handler, msg_id: str, payload: dict) -> None:
        """Execute a single task and acknowledge on success."""
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
        finally:
            self._in_flight_ids.discard(msg_id)
            self._semaphore.release()
