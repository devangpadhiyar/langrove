"""API endpoints for runs -- streaming, wait, background, and thread-bound."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from starlette.responses import StreamingResponse

from langrove.api.deps import (
    authorize,
    get_auth_user,
    get_checkpointer,
    get_db,
    get_graph_registry,
    get_redis,
    get_store,
    get_task_broker,
)
from langrove.db.assistant_repo import AssistantRepository
from langrove.db.pool import DatabasePool
from langrove.db.run_repo import RunRepository
from langrove.db.thread_repo import ThreadRepository
from langrove.graph.registry import GraphRegistry
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
    store=Depends(get_store),
    redis=Depends(get_redis),
    task_broker=Depends(get_task_broker),
) -> RunService:
    return RunService(
        run_repo=RunRepository(db),
        thread_repo=ThreadRepository(db),
        assistant_repo=AssistantRepository(db),
        executor=RunExecutor(registry, checkpointer, store=store),
        publisher=TaskPublisher(task_broker),
        redis=redis,
    )


def _get_broker(redis=Depends(get_redis)) -> EventBroker:
    return EventBroker(redis)


def _user_dict(request: Request) -> dict | None:
    """Serialize the auth user to a dict for graph configurable injection."""
    user = get_auth_user(request)
    if user is None:
        return None
    if hasattr(user, "to_dict"):
        return user.to_dict()
    return {"identity": getattr(user, "identity", "anonymous")}


_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def _sse_response(
    run_id: str,
    stream,
    request: Request | None = None,
    service: RunService | None = None,
) -> StreamingResponse:
    """Create an SSE StreamingResponse with proper headers.

    When request and service are provided, detects client disconnect and
    cancels the run (on_disconnect=cancel behaviour).
    """

    async def generate():
        yield format_sse(metadata_event(run_id))
        async for part in stream:
            if request is not None and await request.is_disconnected():
                if service is not None:
                    await service.cancel_run(UUID(run_id))
                break
            yield format_sse(part)
            if part.event in ("end", "error"):
                break
        else:
            yield format_sse(end_event())

    return StreamingResponse(generate(), media_type="text/event-stream", headers=_SSE_HEADERS)


def _join_stream_response(
    run_id: str,
    broker: EventBroker,
    last_event_id: str | None,
    request: Request | None = None,
    service: RunService | None = None,
) -> StreamingResponse:
    """Join a background run's SSE stream, optionally cancelling on disconnect."""

    if request is None or service is None:
        return StreamingResponse(
            broker.join_stream(run_id, last_event_id=last_event_id),
            media_type="text/event-stream",
            headers=_SSE_HEADERS,
        )

    async def generate():
        async for sse_str in broker.join_stream(run_id, last_event_id=last_event_id):
            if await request.is_disconnected():
                await service.cancel_run(UUID(run_id))
                break
            yield sse_str

    return StreamingResponse(generate(), media_type="text/event-stream", headers=_SSE_HEADERS)


# --- Stateless runs ---


@router.post("/runs/stream")
async def stateless_stream(
    request: Request,
    body: RunCreate,
    service: RunService = Depends(_get_service),
    broker: EventBroker = Depends(_get_broker),
):
    """Create an ephemeral thread, stream the run, auto-delete thread."""
    await authorize(request, "runs", "create", body.model_dump(exclude_none=True))
    auth_user = _user_dict(request)
    if body.on_disconnect == "continue":
        run = await service.background_run(body, auth_user=auth_user)
        run_id = str(run.run_id)
        return StreamingResponse(
            broker.join_stream(run_id), media_type="text/event-stream", headers=_SSE_HEADERS
        )
    run_id, stream = await service.stream_run(body, auth_user=auth_user)
    return _sse_response(run_id, stream, request=request, service=service)


@router.post("/runs/wait", response_model=RunWaitResponse)
async def stateless_wait(
    request: Request,
    body: RunCreate,
    service: RunService = Depends(_get_service),
):
    """Create an ephemeral thread, execute run, return final state."""
    await authorize(request, "runs", "create", body.model_dump(exclude_none=True))
    return await service.wait_run(body, auth_user=_user_dict(request))


# --- Background runs ---


@router.post("/runs", response_model=Run)
async def create_background_run(
    request: Request,
    body: RunCreate,
    service: RunService = Depends(_get_service),
):
    """Create a background run and dispatch to the worker."""
    await authorize(request, "runs", "create", body.model_dump(exclude_none=True))
    return await service.background_run(body, auth_user=_user_dict(request))


@router.post("/runs/search", response_model=list[Run])
async def search_runs(
    request: Request,
    body: RunSearchRequest,
    service: RunService = Depends(_get_service),
):
    await authorize(request, "runs", "search", body.model_dump(exclude_none=True))
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
    return _join_stream_response(
        str(run_id),
        broker,
        last_event_id,
        request=request if cancel_on_disconnect else None,
        service=service if cancel_on_disconnect else None,
    )


# --- Thread-bound runs ---


@router.post("/threads/{thread_id}/runs/stream")
async def thread_stream(
    request: Request,
    thread_id: UUID,
    body: RunCreate,
    service: RunService = Depends(_get_service),
    broker: EventBroker = Depends(_get_broker),
):
    """Stream a run on an existing thread."""
    await authorize(request, "threads", "create_run", body.model_dump(exclude_none=True))
    auth_user = _user_dict(request)
    if body.on_disconnect == "continue":
        run = await service.background_run(body, thread_id=thread_id, auth_user=auth_user)
        run_id = str(run.run_id)
        return StreamingResponse(
            broker.join_stream(run_id), media_type="text/event-stream", headers=_SSE_HEADERS
        )
    run_id, stream = await service.stream_run(body, thread_id=thread_id, auth_user=auth_user)
    return _sse_response(run_id, stream, request=request, service=service)


@router.post("/threads/{thread_id}/runs/wait", response_model=RunWaitResponse)
async def thread_wait(
    request: Request,
    thread_id: UUID,
    body: RunCreate,
    service: RunService = Depends(_get_service),
):
    """Execute a blocking run on an existing thread."""
    await authorize(request, "threads", "create_run", body.model_dump(exclude_none=True))
    return await service.wait_run(body, thread_id=thread_id, auth_user=_user_dict(request))


@router.post("/threads/{thread_id}/runs", response_model=Run)
async def create_thread_background_run(
    request: Request,
    thread_id: UUID,
    body: RunCreate,
    service: RunService = Depends(_get_service),
):
    """Create a background run on a thread and dispatch to the worker."""
    await authorize(request, "threads", "create_run", body.model_dump(exclude_none=True))
    return await service.background_run(body, thread_id=thread_id, auth_user=_user_dict(request))


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
    return _join_stream_response(
        str(run_id),
        broker,
        last_event_id,
        request=request if cancel_on_disconnect else None,
        service=service if cancel_on_disconnect else None,
    )


@router.post("/threads/{thread_id}/runs/{run_id}/cancel", status_code=204)
async def cancel_thread_run(
    thread_id: UUID,
    run_id: UUID,
    service: RunService = Depends(_get_service),
):
    await service.cancel_run(run_id)
    return Response(status_code=204)
