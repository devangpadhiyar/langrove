"""Dead-letter admin API for inspecting and retrying failed tasks."""

from __future__ import annotations

from uuid import UUID

import orjson
from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from langrove.api.deps import get_db, get_redis, get_task_broker
from langrove.db.pool import DatabasePool
from langrove.db.run_repo import RunRepository
from langrove.exceptions import NotFoundError
from langrove.queue.tasks import DEAD_LETTER_STREAM

router = APIRouter(prefix="/dead-letter", tags=["dead-letter"])


@router.get("")
async def list_dead_letters(
    limit: int = Query(default=20, ge=1, le=100),
    redis=Depends(get_redis),
):
    """List dead-lettered tasks."""
    try:
        entries = await redis.xrange(DEAD_LETTER_STREAM, count=limit)
    except Exception:
        return []

    return [
        {
            "message_id": msg_id,
            "payload": orjson.loads(fields["payload"]) if "payload" in fields else fields,
        }
        for msg_id, fields in entries
    ]


@router.get("/{message_id}")
async def get_dead_letter(message_id: str, redis=Depends(get_redis)):
    """Get a single dead-lettered task."""
    entries = await redis.xrange(DEAD_LETTER_STREAM, min=message_id, max=message_id, count=1)
    if not entries:
        raise NotFoundError("dead-letter", message_id)
    msg_id, fields = entries[0]
    return {
        "message_id": msg_id,
        "payload": orjson.loads(fields["payload"]) if "payload" in fields else fields,
    }


@router.post("/{message_id}/retry", status_code=204)
async def retry_dead_letter(
    message_id: str,
    redis=Depends(get_redis),
    db: DatabasePool = Depends(get_db),
    task_broker=Depends(get_task_broker),
):
    """Re-enqueue a dead-lettered task for retry via the Taskiq broker."""
    entries = await redis.xrange(DEAD_LETTER_STREAM, min=message_id, max=message_id, count=1)
    if not entries:
        raise NotFoundError("dead-letter", message_id)
    _, fields = entries[0]

    # Re-enqueue via Taskiq so it goes through the normal pipeline
    if "payload" in fields:
        from taskiq import TaskiqMessage

        payload = orjson.loads(fields["payload"])
        run_id = payload.get("run_id", "")

        msg = TaskiqMessage(
            task_id=run_id,
            task_name="handle_run",
            labels={},
            args=[],
            kwargs=payload,
        )
        await task_broker.kick(msg)

        # Remove from dead-letter stream
        await redis.xdel(DEAD_LETTER_STREAM, message_id)

        # Reset run status back to pending
        if run_id:
            run_repo = RunRepository(db)
            await run_repo.update_status(UUID(run_id), "pending")

    return Response(status_code=204)
