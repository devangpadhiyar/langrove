"""Dead-letter admin API for inspecting and retrying failed tasks."""

from __future__ import annotations

from uuid import UUID

import orjson
from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from langrove.api.deps import get_db, get_redis
from langrove.db.pool import DatabasePool
from langrove.db.run_repo import RunRepository
from langrove.exceptions import NotFoundError
from langrove.queue.consumer import DEAD_LETTER_STREAM
from langrove.queue.publisher import TASK_STREAM

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
):
    """Re-publish a dead-lettered task for retry."""
    entries = await redis.xrange(DEAD_LETTER_STREAM, min=message_id, max=message_id, count=1)
    if not entries:
        raise NotFoundError("dead-letter", message_id)
    _, fields = entries[0]

    # Re-publish to task stream
    await redis.xadd(TASK_STREAM, fields)
    # Remove from dead-letter
    await redis.xdel(DEAD_LETTER_STREAM, message_id)

    # Reset run status back to pending
    if "payload" in fields:
        payload = orjson.loads(fields["payload"])
        run_id = payload.get("run_id")
        if run_id:
            run_repo = RunRepository(db)
            await run_repo.update_status(UUID(run_id), "pending")

    return Response(status_code=204)
