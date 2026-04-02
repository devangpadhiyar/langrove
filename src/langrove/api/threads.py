"""API endpoints for threads."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

from langrove.api.deps import get_checkpointer, get_db, get_graph_registry
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
    body: ThreadCreate,
    service: ThreadService = Depends(_get_service),
):
    return await service.create(body)


@router.get("/{thread_id}", response_model=Thread)
async def get_thread(
    thread_id: UUID,
    service: ThreadService = Depends(_get_service),
):
    return await service.get(thread_id)


@router.patch("/{thread_id}", response_model=Thread)
async def update_thread(
    thread_id: UUID,
    body: ThreadPatch,
    service: ThreadService = Depends(_get_service),
):
    return await service.update(thread_id, body)


@router.delete("/{thread_id}", status_code=204)
async def delete_thread(
    thread_id: UUID,
    service: ThreadService = Depends(_get_service),
):
    await service.delete(thread_id)
    return Response(status_code=204)


@router.post("/search", response_model=list[Thread])
async def search_threads(
    body: ThreadSearchRequest,
    service: ThreadService = Depends(_get_service),
):
    return await service.search(body)


@router.post("/{thread_id}/copy", response_model=Thread)
async def copy_thread(
    thread_id: UUID,
    service: ThreadService = Depends(_get_service),
):
    return await service.copy(thread_id)


@router.get("/{thread_id}/state", response_model=ThreadState)
async def get_thread_state(
    thread_id: UUID,
    checkpoint_id: str | None = Query(default=None),
    service: ThreadService = Depends(_get_service),
):
    return await service.get_state(thread_id, checkpoint_id)


@router.post("/{thread_id}/state", response_model=ThreadState)
async def update_thread_state(
    thread_id: UUID,
    body: ThreadStateUpdate,
    service: ThreadService = Depends(_get_service),
):
    return await service.update_state(thread_id, body)


@router.get("/{thread_id}/history", response_model=list[ThreadState])
async def get_thread_history(
    thread_id: UUID,
    limit: int = Query(default=10, ge=1, le=100),
    before: str | None = Query(default=None),
    service: ThreadService = Depends(_get_service),
):
    req = ThreadHistoryRequest(limit=limit, before=before)
    return await service.get_history(thread_id, req)
