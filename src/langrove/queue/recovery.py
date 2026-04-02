"""Recovery monitor -- reclaims stuck tasks via XAUTOCLAIM."""

from __future__ import annotations

import asyncio
from typing import Any

import orjson

from langrove.queue.publisher import TASK_STREAM
from langrove.queue.consumer import CONSUMER_GROUP, DEAD_LETTER_STREAM


class RecoveryMonitor:
    """Monitors for stuck tasks and reclaims them.

    Runs periodically to:
    1. XAUTOCLAIM tasks pending longer than timeout
    2. Move poison messages (>max_attempts) to dead-letter stream
    """

    def __init__(
        self,
        redis: Any,
        *,
        timeout_ms: int = 60000,
        max_attempts: int = 3,
        interval_seconds: int = 30,
    ):
        self._redis = redis
        self._timeout_ms = timeout_ms
        self._max_attempts = max_attempts
        self._interval = interval_seconds

    async def run(self, on_reclaim=None) -> None:
        """Run the recovery monitor loop.

        on_reclaim: optional async callback(run_id) when a task is dead-lettered.
        """
        while True:
            try:
                await self._check_stale_tasks(on_reclaim)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Recovery monitor error: {e}")

            await asyncio.sleep(self._interval)

    async def _check_stale_tasks(self, on_reclaim=None) -> None:
        """Reclaim stale tasks and handle poison messages."""
        try:
            result = await self._redis.xautoclaim(
                TASK_STREAM,
                CONSUMER_GROUP,
                "recovery-monitor",
                min_idle_time=self._timeout_ms,
                start_id="0",
                count=10,
            )
        except Exception:
            return

        if not result or len(result) < 2:
            return

        # result = (next_start_id, [(msg_id, fields), ...], [deleted_ids])
        claimed_messages = result[1] if len(result) > 1 else []

        for msg_id, fields in claimed_messages:
            if not fields:
                continue

            # Check delivery count via XPENDING
            try:
                pending_info = await self._redis.xpending_range(
                    TASK_STREAM, CONSUMER_GROUP,
                    min=msg_id, max=msg_id, count=1,
                )

                if pending_info and pending_info[0].get("times_delivered", 0) > self._max_attempts:
                    # Poison message -- move to dead letter
                    await self._redis.xadd(DEAD_LETTER_STREAM, fields)
                    await self._redis.xack(TASK_STREAM, CONSUMER_GROUP, msg_id)
                    await self._redis.xdel(TASK_STREAM, msg_id)

                    if on_reclaim and "payload" in fields:
                        payload = orjson.loads(fields["payload"])
                        await on_reclaim(payload.get("run_id"))

                    print(f"Dead-lettered task: {msg_id}")

            except Exception as e:
                print(f"Error checking pending info for {msg_id}: {e}")
