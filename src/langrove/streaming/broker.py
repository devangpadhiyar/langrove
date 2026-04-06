"""Event broker for relaying stream events.

- Foreground runs: direct asyncio.Queue (same process)
- Background runs: Redis pub/sub (cross-process)
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import orjson

from langrove.models.common import StreamPart
from langrove.streaming.formatter import format_sse, format_sse_with_id


def _default(obj: Any) -> Any:
    """orjson fallback for LangChain message objects and other non-serializable types."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "dict"):
        return obj.dict()
    raise TypeError(f"Type is not JSON serializable: {type(obj).__name__}")


class EventBroker:
    """Routes stream events between producers and consumers.

    For foreground runs: uses local asyncio queues.
    For background runs: uses Redis pub/sub.
    """

    def __init__(self, redis: Any | None = None):
        self._redis = redis
        self._local_queues: dict[str, list[asyncio.Queue]] = {}

    def subscribe_local(self, run_id: str) -> asyncio.Queue:
        """Subscribe to events for a foreground run (same process)."""
        queue: asyncio.Queue = asyncio.Queue()
        if run_id not in self._local_queues:
            self._local_queues[run_id] = []
        self._local_queues[run_id].append(queue)
        return queue

    async def publish_local(self, run_id: str, part: StreamPart) -> None:
        """Publish an event to all local subscribers."""
        queues = self._local_queues.get(run_id, [])
        for q in queues:
            await q.put(part)

    def unsubscribe_local(self, run_id: str, queue: asyncio.Queue) -> None:
        """Remove a local subscriber."""
        queues = self._local_queues.get(run_id, [])
        if queue in queues:
            queues.remove(queue)
        if not queues:
            self._local_queues.pop(run_id, None)

    async def publish_redis(
        self,
        run_id: str,
        part: StreamPart,
        event_id: str | None = None,
    ) -> None:
        """Publish an event via Redis pub/sub (for background runs)."""
        if self._redis is None:
            return
        channel = f"langrove:runs:{run_id}:stream"
        data = orjson.dumps(
            {"event": part.event, "data": part.data, "event_id": event_id},
            default=_default,
        )
        await self._redis.publish(channel, data)

    async def subscribe_redis(self, run_id: str) -> AsyncIterator[StreamPart]:
        """Subscribe to events via Redis pub/sub (for background runs)."""
        if self._redis is None:
            return

        channel = f"langrove:runs:{run_id}:stream"
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(channel)

        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    payload = orjson.loads(message["data"])
                    part = StreamPart(payload["event"], payload["data"])
                    yield part
                    if part.event in ("end", "error"):
                        break
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()

    async def store_event(self, run_id: str, part: StreamPart, event_id: str) -> None:
        """Store an event in Redis Stream for replay/reconnection."""
        if self._redis is None:
            return
        stream_key = f"langrove:runs:{run_id}:events"
        data = orjson.dumps({"event": part.event, "data": part.data}, default=_default).decode()
        await self._redis.xadd(stream_key, {"data": data, "id": event_id})

    async def join_stream(
        self,
        run_id: str,
        last_event_id: str | None = None,
    ) -> AsyncIterator[str]:
        """Join an ongoing or completed background run's SSE event stream.

        Subscribe-first pattern: subscribes to pub/sub before reading stored
        events so no events are missed in the gap. Deduplicates by event ID.

        Yields formatted SSE strings ready for StreamingResponse.
        """
        if self._redis is None:
            return

        seen_ids: set[str] = set()
        channel = f"langrove:runs:{run_id}:stream"
        stream_key = f"langrove:runs:{run_id}:events"

        # Step 1: Subscribe to pub/sub FIRST to capture events during replay
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(channel)

        try:
            # Step 2: Replay stored events from Redis Stream
            entries = await self._redis.xrange(stream_key, min="-", max="+")
            past_last = last_event_id is None
            run_finished = False

            for _, fields in entries:
                event_id = fields.get("id", "")
                payload = orjson.loads(fields["data"])
                part = StreamPart(payload["event"], payload["data"])

                if not past_last:
                    if event_id == last_event_id:
                        past_last = True
                    continue

                seen_ids.add(event_id)
                yield format_sse_with_id(part, event_id)

                if part.event in ("end", "error"):
                    run_finished = True

            if run_finished:
                return

            # Step 3: Drain live pub/sub events, deduplicating
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue

                payload = orjson.loads(message["data"])
                part = StreamPart(payload["event"], payload["data"])
                event_id = payload.get("event_id") or ""

                if event_id and event_id in seen_ids:
                    continue

                if event_id:
                    seen_ids.add(event_id)
                    yield format_sse_with_id(part, event_id)
                else:
                    yield format_sse(part)

                if part.event in ("end", "error"):
                    break
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()

    async def replay_events(self, run_id: str, after_id: str) -> AsyncIterator[StreamPart]:
        """Replay stored events after a given ID (for reconnection)."""
        if self._redis is None:
            return
        stream_key = f"langrove:runs:{run_id}:events"
        events = await self._redis.xrange(stream_key, min=f"({after_id}", max="+")
        for _, fields in events:
            payload = orjson.loads(fields["data"])
            yield StreamPart(payload["event"], payload["data"])
