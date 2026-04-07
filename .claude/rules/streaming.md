---
description: SSE wire format, event types, stream modes, pub/sub broker, and event replay
globs:
  - "src/langrove/streaming/**/*.py"
---

# Streaming

## SSE Wire Format (useStream / LangGraph SDK compatible)
- Format: `event: {name}\ndata: {json}\n\n` — double newline terminates each event
- Content-Type: `text/event-stream`
- Optional reconnection: `id: {event_id}` line before data line

## Event Sequence
1. `metadata` — always first: `{"run_id": "..."}`
2. `values` / `updates` / `messages` — graph execution events
3. `end` — always last: `data: null` (literal null, not omitted)
4. `error` — terminal on exception: `{"error": "...", "message": "ExceptionType"}`

## Stream Modes
- Input can be string or list: `stream_mode: str | list[str]`
- Langrove internally adds "updates" (always) for interrupt detection
- "messages" mode also adds "messages-tuple" internally (SDK convenience)
- SDK-internal modes ("events", "messages-tuple") stripped before processing chunks

## Chunk Processing (executor.py)
LangGraph `astream()` output varies by configuration:
- Single mode, no subgraphs: bare `chunk`
- Multi-mode, no subgraphs: `(mode, chunk)` tuple
- Single mode, subgraphs=True: `(namespace_tuple, chunk)`
- Multi-mode, subgraphs=True: `(namespace_tuple, mode, chunk)`

## Subgraph Namespace
- Pipe-delimited event names: `updates|parent|child`
- SDK parses pipes to route subagent messages to correct handler
- Supports arbitrary nesting depth

## Messages Mode
- Chunks are `(BaseMessageChunk, metadata_dict)` tuples
- Serialized via `model_dump()` (Pydantic v2) or `dict()` (Pydantic v1)
- If message is already a dict (not Pydantic), use as-is

## Updates Mode
- Contains interrupts as `__interrupt__` key: `{"__interrupt__": [...]}`
- Only forwarded as SSE if explicitly requested OR contains interrupt data
- Prevents duplicate state broadcasts

## JSON Serialization
- `_default(obj)` fallback: tries `obj.model_dump()` → `obj.dict()` → TypeError
- Handles LangChain message objects, UUIDs, datetimes (orjson native)

## Event IDs
- Format: `{run_id}_event_{counter}` — monotonically increasing
- Must be sortable for Redis XRANGE replay
- Client sends `Last-Event-ID` header on reconnect

## Event Broker Architecture
- **Foreground runs (same process):** `asyncio.Queue` per run_id in `_local_queues` dict
- **Background runs (cross-process):** Redis pub/sub channel `langrove:runs:{run_id}:stream`
- **Event storage:** Redis Streams `langrove:runs:{run_id}:events` (TTL configurable, default 24h)

## Event Replay (subscribe-first pattern)
1. Subscribe to pub/sub FIRST (captures events during replay gap)
2. Replay stored events via XRANGE from "-" to "+"
3. Skip events until `last_event_id` found
4. Yield stored events, tracking seen IDs in `seen_ids` set
5. Drain live pub/sub, deduplicating by ID
6. Stop on "end" or "error" event

## Gotchas
- Redis pub/sub doesn't persist — messages lost if no subscribers present
- `end` event data is `null`, not omitted: `data: null\n`
- `asyncio.aclosing()` required for astream() generator cleanup (releases checkpoint locks)
- Implicitly added `values` mode is suppressed if not in user's original request
