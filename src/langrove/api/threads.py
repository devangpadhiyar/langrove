"""API endpoints for threads."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from langrove.api.deps import (
    authorize,
    authorize_read,
    get_checkpointer,
    get_db,
    get_graph_registry,
)
from langrove.db.pool import DatabasePool
from langrove.db.thread_repo import ThreadRepository
from langrove.graph.registry import GraphRegistry
from langrove.models.threads import (
    Thread,
    ThreadCreate,
    ThreadHistoryRequest,
    ThreadPatch,
    ThreadSearchRequest,
    ThreadState,
    ThreadStateUpdate,
)
from langrove.services.thread_service import ThreadService

router = APIRouter(prefix="/threads", tags=["threads"])


def _get_service(
    db: DatabasePool = Depends(get_db),
    checkpointer=Depends(get_checkpointer),
    registry: GraphRegistry = Depends(get_graph_registry),
) -> ThreadService:
    return ThreadService(ThreadRepository(db), checkpointer, registry)


@router.post("", response_model=Thread)
async def create_thread(
    request: Request,
    body: ThreadCreate,
    service: ThreadService = Depends(_get_service),
):
    value = await authorize(request, "threads", "create", body.model_dump(exclude_none=True))
    # Merge auth filters (e.g. team_id) into thread metadata so resources are
    # properly scoped and discoverable via search.
    if isinstance(value, dict) and value:
        merged_meta = {**(body.metadata or {}), **value}
        body = ThreadCreate(
            **{
                **body.model_dump(exclude_none=True),
                "metadata": merged_meta,
            }
        )
    return await service.create(body)


@router.get("/{thread_id}", response_model=Thread)
async def get_thread(
    request: Request,
    thread_id: UUID,
    service: ThreadService = Depends(_get_service),
):
    thread = await service.get(thread_id)
    await authorize_read(request, "threads", thread.metadata)
    return thread


@router.patch("/{thread_id}", response_model=Thread)
async def update_thread(
    request: Request,
    thread_id: UUID,
    body: ThreadPatch,
    service: ThreadService = Depends(_get_service),
):
    await authorize(
        request, "threads", "update", {"thread_id": str(thread_id), "metadata": body.metadata}
    )
    return await service.update(thread_id, body)


@router.delete("/{thread_id}", status_code=204)
async def delete_thread(
    request: Request,
    thread_id: UUID,
    service: ThreadService = Depends(_get_service),
):
    await authorize(request, "threads", "delete", {"thread_id": str(thread_id)})
    return await service.delete(thread_id)


@router.post("/search", response_model=list[Thread])
async def search_threads(
    request: Request,
    body: ThreadSearchRequest,
    service: ThreadService = Depends(_get_service),
):
    filters = await authorize(request, "threads", "search", body.model_dump(exclude_none=True))
    if isinstance(filters, dict) and filters != body.model_dump(exclude_none=True):
        body_dict = body.model_dump(exclude_none=True)
        body_dict.setdefault("metadata", {}).update(filters)
        body = ThreadSearchRequest(**body_dict)
    return await service.search(body)


@router.post("/{thread_id}/copy", response_model=Thread)
async def copy_thread(
    request: Request,
    thread_id: UUID,
    service: ThreadService = Depends(_get_service),
):
    await authorize_read(request, "threads", (await service.get(thread_id)).metadata)
    return await service.copy(thread_id)


@router.get("/{thread_id}/state", response_model=ThreadState)
async def get_thread_state(
    request: Request,
    thread_id: UUID,
    checkpoint_id: str | None = Query(default=None),
    service: ThreadService = Depends(_get_service),
):
    await authorize_read(request, "threads", (await service.get(thread_id)).metadata)
    return await service.get_state(thread_id, checkpoint_id)


@router.post("/{thread_id}/state", response_model=ThreadState)
async def update_thread_state(
    request: Request,
    thread_id: UUID,
    body: ThreadStateUpdate,
    service: ThreadService = Depends(_get_service),
):
    await authorize(request, "threads", "update", {"thread_id": str(thread_id)})
    return await service.update_state(thread_id, body)


@router.get("/{thread_id}/history", response_model=list[ThreadState])
async def get_thread_history_get(
    request: Request,
    thread_id: UUID,
    limit: int = Query(default=10, ge=1, le=100),
    before: str | None = Query(default=None),
    service: ThreadService = Depends(_get_service),
):
    await authorize_read(request, "threads", (await service.get(thread_id)).metadata)
    req = ThreadHistoryRequest(limit=limit, before=before)
    return await service.get_history(thread_id, req)


@router.post("/{thread_id}/history", response_model=list[ThreadState])
async def get_thread_history_post(
    request: Request,
    thread_id: UUID,
    body: ThreadHistoryRequest = ThreadHistoryRequest(),
    service: ThreadService = Depends(_get_service),
):
    await authorize_read(request, "threads", (await service.get(thread_id)).metadata)
    return await service.get_history(thread_id, body)
