"""API endpoints for runs -- streaming, wait, background, and thread-bound."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from starlette.responses import StreamingResponse

from langrove.api.deps import get_checkpointer, get_db, get_graph_registry, get_redis
from langrove.db.assistant_repo import AssistantRepository
from langrove.db.pool import DatabasePool
from langrove.db.run_repo import RunRepository
from langrove.db.thread_repo import ThreadRepository
from langrove.graph.registry import GraphRegistry
from langrove.models.common import StreamPart
from langrove.models.runs import Run, RunCreate, RunSearchRequest, RunWaitResponse
from langrove.queue.publisher import TaskPublisher
from langrove.services.run_service import RunService
from langrove.streaming.broker import EventBroker
from langrove.streaming.executor import RunExecutor
from langrove.streaming.formatter import end_event, format_sse, metadata_event

router = APIRouter(tags=["runs"])


def _get_service(
    db: DatabasePool = Depends(get_db),
    registry: GraphRegistry = Depends(get_graph_registry),
    checkpointer=Depends(get_checkpointer),
    redis=Depends(get_redis),
) -> RunService:
    return RunService(
        run_repo=RunRepository(db),
        thread_repo=ThreadRepository(db),
        assistant_repo=AssistantRepository(db),
        executor=RunExecutor(registry, checkpointer),
        publisher=TaskPublisher(redis),
    )


def _get_broker(redis=Depends(get_redis)) -> EventBroker:
    return EventBroker(redis)


def _sse_response(run_id: str, stream) -> StreamingResponse:
    """Create an SSE StreamingResponse with proper headers."""

    async def generate():
        # First event: metadata
        yield format_sse(metadata_event(run_id))

        # Stream events
        async for part in stream:
            yield format_sse(part)

        # Last event: end
        yield format_sse(end_event())

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# --- Stateless runs ---

@router.post("/runs/stream")
async def stateless_stream(
    body: RunCreate,
    service: RunService = Depends(_get_service),
):
    """Create an ephemeral thread, stream the run, auto-delete thread."""
    run_id, stream = await service.stream_run(body)
    return _sse_response(run_id, stream)


@router.post("/runs/wait", response_model=RunWaitResponse)
async def stateless_wait(
    body: RunCreate,
    service: RunService = Depends(_get_service),
):
    """Create an ephemeral thread, execute run, return final state."""
    return await service.wait_run(body)


# --- Background runs ---

@router.post("/runs", response_model=Run)
async def create_background_run(
    body: RunCreate,
    service: RunService = Depends(_get_service),
):
    """Create a background run and dispatch to the worker."""
    return await service.background_run(body)


@router.post("/runs/search", response_model=list[Run])
async def search_runs(
    body: RunSearchRequest,
    service: RunService = Depends(_get_service),
):
    return await service.search_runs(body)


@router.get("/runs/{run_id}", response_model=Run)
async def get_run(
    run_id: UUID,
    service: RunService = Depends(_get_service),
):
    return await service.get_run(run_id)


@router.post("/runs/{run_id}/cancel", status_code=204)
async def cancel_run(
    run_id: UUID,
    service: RunService = Depends(_get_service),
):
    await service.cancel_run(run_id)
    return Response(status_code=204)


@router.delete("/runs/{run_id}", status_code=204)
async def delete_run(
    run_id: UUID,
    service: RunService = Depends(_get_service),
):
    await service.delete_run(run_id)
    return Response(status_code=204)


# --- Join background runs ---

@router.get("/runs/{run_id}/stream")
async def join_run_stream(
    run_id: UUID,
    request: Request,
    cancel_on_disconnect: bool = Query(default=False),
    service: RunService = Depends(_get_service),
    broker: EventBroker = Depends(_get_broker),
):
    """Join a background run's SSE event stream."""
    await service.get_run(run_id)
    last_event_id = request.headers.get("last-event-id")
    return StreamingResponse(
        broker.join_stream(str(run_id), last_event_id=last_event_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# --- Thread-bound runs ---

@router.post("/threads/{thread_id}/runs/stream")
async def thread_stream(
    thread_id: UUID,
    body: RunCreate,
    service: RunService = Depends(_get_service),
):
    """Stream a run on an existing thread."""
    run_id, stream = await service.stream_run(body, thread_id=thread_id)
    return _sse_response(run_id, stream)


@router.post("/threads/{thread_id}/runs/wait", response_model=RunWaitResponse)
async def thread_wait(
    thread_id: UUID,
    body: RunCreate,
    service: RunService = Depends(_get_service),
):
    """Execute a blocking run on an existing thread."""
    return await service.wait_run(body, thread_id=thread_id)


@router.post("/threads/{thread_id}/runs", response_model=Run)
async def create_thread_background_run(
    thread_id: UUID,
    body: RunCreate,
    service: RunService = Depends(_get_service),
):
    """Create a background run on a thread and dispatch to the worker."""
    return await service.background_run(body, thread_id=thread_id)


@router.get("/threads/{thread_id}/runs", response_model=list[Run])
async def list_thread_runs(
    thread_id: UUID,
    limit: int = Query(default=10, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    service: RunService = Depends(_get_service),
):
    return await service.list_thread_runs(thread_id, limit=limit, offset=offset)


@router.get("/threads/{thread_id}/runs/{run_id}", response_model=Run)
async def get_thread_run(
    thread_id: UUID,
    run_id: UUID,
    service: RunService = Depends(_get_service),
):
    return await service.get_run(run_id)


@router.get("/threads/{thread_id}/runs/{run_id}/stream")
async def join_thread_run_stream(
    thread_id: UUID,
    run_id: UUID,
    request: Request,
    cancel_on_disconnect: bool = Query(default=False),
    service: RunService = Depends(_get_service),
    broker: EventBroker = Depends(_get_broker),
):
    """Join a thread-bound background run's SSE event stream."""
    await service.get_run(run_id)
    last_event_id = request.headers.get("last-event-id")
    return StreamingResponse(
        broker.join_stream(str(run_id), last_event_id=last_event_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/threads/{thread_id}/runs/{run_id}/cancel", status_code=204)
async def cancel_thread_run(
    thread_id: UUID,
    run_id: UUID,
    service: RunService = Depends(_get_service),
):
    await service.cancel_run(run_id)
    return Response(status_code=204)
